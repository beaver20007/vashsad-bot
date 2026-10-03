"""Фаза 1: Запись на консультацию — FSM с выбором слота, всё кнопками (без команд для клиента).

Часовой пояс (докс-трек А, 2026-10-03): slot_dt хранится и везде трактуется как
московское «настенное» время (naive datetime без tzinfo, по смыслу — Europe/Moscow).
Контейнер Railway работает в UTC (проверено `railway ssh`), поэтому создание слотов и
сравнения "сейчас" делаются явно через zoneinfo, а не через datetime.now()/SQL NOW().
См. docs/ORCHESTRATOR.md, запись "fix/fsm-data-ttl-margin"-смежная по духу, и запись
этого трека.
"""
import html
import logging
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import (
    BOOKING_AUTOSLOTS_DURATION_MIN,
    BOOKING_AUTOSLOTS_HOURS,
    BOOKING_AUTOSLOTS_WEEKDAYS,
    BOOKING_CONTACT_URL,
    BOOKING_OPEN_FOR_CLIENTS,
    BOOKING_RECIPIENT_IDS,
    BOOKING_SERVICES,
    DESIGNER_NAME,
    DESIGNER_TELEGRAM_ID,
    DESIGNER_TELEGRAM_ID_2,
)
from services.booking_format import ru_day_label, ru_dt_label, ru_dt_label_short
from services.calendar_service import build_google_calendar_url, generate_ics
from services.database import get_pool

router = Router()
log = logging.getLogger(__name__)

MOSCOW_TZ = ZoneInfo("Europe/Moscow")

# Часы, из которых сотрудник может выбрать время при ручном добавлении
# отдельного слота (кнопками). Автогенерация и "слоты на неделю" используют
# свой список из конфига (BOOKING_AUTOSLOTS_HOURS) — здесь более широкий
# набор специально для точечного добавления.
MANUAL_SLOT_HOURS = (9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19)

# Сколько дней вперёд предлагать сотруднику при точечном добавлении слота.
MANUAL_SLOT_DAYS_AHEAD = 14


class BookingForm(StatesGroup):
    waiting_service       = State()
    waiting_slot          = State()
    waiting_phone_consent = State()
    waiting_contact       = State()


class BookingRequest(StatesGroup):
    """Свободная заявка, когда слотов нет/запись не открыта — отдельная ветка
    от BookingForm, не требует выбора слота."""
    waiting_text = State()


# Обязательные поля анкеты записи к моменту ввода телефона (process_contact).
# Без проверки перед прямым data["slot_id"] и т.п. неполная анкета (например,
# data пережила TTL дольше, чем state — см. docs/ORCHESTRATOR.md,
# fix/fsm-data-ttl-margin) роняет хендлер с KeyError.
BOOKING_REQUIRED_FIELDS = ("slot_id", "slot_dt", "service_key", "service_price")

BOOKING_RETRY_TEXT = (
    "😔 <b>Не получилось оформить запись</b>\n\n"
    "Похоже, анкета была открыта слишком долго, и часть информации "
    "потерялась. Пожалуйста, оформите запись заново."
)

# Клиент прислал не текст (фото/стикер), пустую строку/пробелы, или контакт
# не свой — но данные анкеты (слот и услуга) целы — просим прислать телефон
# ещё раз, не сбрасывая уже сделанный выбор.
BOOKING_PHONE_AS_TEXT = (
    "📞 Пожалуйста, пришлите номер телефона — кнопкой «Поделиться номером» "
    "или обычным текстовым сообщением, так мы сможем подтвердить запись."
)

BOOKING_COMING_SOON_TEXT = (
    "📅 <b>Запись на консультацию скоро откроется</b>\n\n"
    "Мы вот-вот запустим запись прямо в боте. А пока можно оставить заявку "
    "или написать нам напрямую — подберём время вручную."
)

BOOKING_NO_SLOTS_TEXT = (
    "😔 <b>Свободных слотов пока нет</b>\n\n"
    "Можно оставить заявку или написать нам напрямую — подберём удобное время вручную."
)


# ── Доступ сотрудников (позже можно перевести на admin_users) ─────────────

def _booking_staff_ids() -> set[int]:
    """Кто видит экран «⚙️ Управление записью» (команды /slots, /booking_admin).
    Объединение DESIGNER_TELEGRAM_ID/_2 и BOOKING_RECIPIENT_IDS — вне зависимости
    от того, пуст ли BOOKING_RECIPIENT_IDS (в отличие от получателей уведомлений,
    см. _booking_recipient_ids)."""
    ids = set(BOOKING_RECIPIENT_IDS)
    if DESIGNER_TELEGRAM_ID:
        ids.add(DESIGNER_TELEGRAM_ID)
    if DESIGNER_TELEGRAM_ID_2:
        ids.add(DESIGNER_TELEGRAM_ID_2)
    return ids


def _is_booking_staff(telegram_id: int) -> bool:
    return telegram_id in _booking_staff_ids()


def _booking_recipient_ids() -> list[int]:
    """Кто получает уведомление «Новая запись!» / «Заявка». Пусто в конфиге ->
    оба DESIGNER_TELEGRAM_ID/_2, как было до этого трека."""
    if BOOKING_RECIPIENT_IDS:
        return list(BOOKING_RECIPIENT_IDS)
    return [d for d in (DESIGNER_TELEGRAM_ID, DESIGNER_TELEGRAM_ID_2) if d]


def _missing_booking_fields(data: dict) -> list[str]:
    """Имена отсутствующих/пустых обязательных полей анкеты (без значений)."""
    return [f for f in BOOKING_REQUIRED_FIELDS if data.get(f) in (None, "")]


def _own_contact_phone(message: Message) -> str | None:
    """Номер из message.contact, только если контакт принадлежит самому
    отправителю (пересланная чужая визитка не считается номером клиента)."""
    contact = message.contact
    if contact is None:
        return None
    if contact.user_id and contact.user_id != message.from_user.id:
        return None
    return contact.phone_number


def _service_by_key(key: str) -> dict | None:
    return next((s for s in BOOKING_SERVICES if s["key"] == key), None)


def _moscow_now_naive() -> datetime:
    """'Настенное' время Москвы без tzinfo — именно так хранится slot_dt."""
    return datetime.now(MOSCOW_TZ).replace(tzinfo=None)


# Форматирование дат вынесено в services/booking_format.py — его же использует
# services/scheduler.py (напоминания), без циклического импорта между модулями.
_ru_dt_label = ru_dt_label
_ru_dt_label_short = ru_dt_label_short
_ru_day_label = ru_day_label


async def _get_free_slots(days_ahead: int = 14) -> list[dict]:
    """Возвращает свободные слоты на ближайшие N дней (МСК)."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT id, slot_dt, duration_min FROM booking_slots
               WHERE slot_dt > $1 AND slot_dt < $2 AND is_booked = FALSE
               ORDER BY slot_dt LIMIT 60""",
            _moscow_now_naive(), _moscow_now_naive() + timedelta(days=days_ahead),
        )
    return [{"id": r["id"], "dt": r["slot_dt"], "dur": r["duration_min"]} for r in rows]


def _group_slots_by_day(slots: list[dict]) -> dict[date, list[dict]]:
    groups: dict[date, list[dict]] = {}
    for s in slots:
        groups.setdefault(s["dt"].date(), []).append(s)
    return dict(sorted(groups.items()))


def _day_picker_keyboard(slots: list[dict], day_cb_prefix: str, back_cb: str) -> InlineKeyboardMarkup:
    groups = _group_slots_by_day(slots)
    b = InlineKeyboardBuilder()
    for day in groups:
        b.row(InlineKeyboardButton(text=_ru_day_label(day), callback_data=f"{day_cb_prefix}{day.isoformat()}"))
    b.row(InlineKeyboardButton(text="◀️ Назад", callback_data=back_cb))
    return b.as_markup()


def _time_picker_keyboard(slots_for_day: list[dict], time_cb_prefix: str, back_cb: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for s in slots_for_day:
        b.button(text=f"{s['dt'].strftime('%H:%M')} МСК", callback_data=f"{time_cb_prefix}{s['id']}")
    b.adjust(2)
    b.row(InlineKeyboardButton(text="◀️ Другой день", callback_data=back_cb))
    return b.as_markup()


def _booking_coming_soon_keyboard() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    if BOOKING_CONTACT_URL:
        b.row(InlineKeyboardButton(text="✉️ Написать", url=BOOKING_CONTACT_URL))
    b.row(InlineKeyboardButton(text="📝 Оставить заявку", callback_data="book_leave_request"))
    b.row(InlineKeyboardButton(text="◀️ Главное меню", callback_data="menu:main"))
    return b.as_markup()


def _booking_restart_keyboard() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="🔁 Начать запись заново", callback_data="book_restart"))
    b.row(InlineKeyboardButton(text="◀️ Главное меню", callback_data="menu:main"))
    return b.as_markup()


# ── Вход в запись (клиент) ──────────────────────────────────────────────

STAFF_PREVIEW_PREFIX = "🔧 Предпросмотр для сотрудников: клиентам запись пока закрыта.\n\n"


async def _show_service_picker(send, state: FSMContext, telegram_id: int | None = None) -> None:
    """send — message.answer или callback.message.edit_text (одинаковая сигнатура kwargs).

    telegram_id — опционален; при закрытой для клиентов записи (BOOKING_OPEN_FOR_CLIENTS=false)
    сотрудник (см. _is_booking_staff) всё равно видит обычный выбор формата — с пометкой
    "предпросмотр" — чтобы можно было пройти сценарий записи без открытия её клиентам."""
    staff_preview = (
        not BOOKING_OPEN_FOR_CLIENTS and telegram_id is not None and _is_booking_staff(telegram_id)
    )
    if not BOOKING_OPEN_FOR_CLIENTS and not staff_preview:
        await send(BOOKING_COMING_SOON_TEXT, parse_mode="HTML", reply_markup=_booking_coming_soon_keyboard())
        await state.clear()
        return
    b = InlineKeyboardBuilder()
    for svc in BOOKING_SERVICES:
        price_label = f"{svc['price']:,}".replace(",", " ")
        b.row(InlineKeyboardButton(
            text=f"{svc['label']} — {price_label} ₽ ({svc['duration_min']} мин)",
            callback_data=f"book_svc:{svc['key']}",
        ))
    b.row(InlineKeyboardButton(text="◀️ Главное меню", callback_data="menu:main"))
    prefix = STAFF_PREVIEW_PREFIX if staff_preview else ""
    await send(
        f"{prefix}📅 <b>Запись на консультацию</b>\n\nВыберите формат:",
        parse_mode="HTML",
        reply_markup=b.as_markup(),
    )
    await state.set_state(BookingForm.waiting_service)


@router.message(Command("book"))
async def cmd_book(message: Message, state: FSMContext):
    await _show_service_picker(message.answer, state, message.from_user.id)


@router.callback_query(F.data == "menu:book")
async def cb_menu_book(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await _show_service_picker(callback.message.edit_text, state, callback.from_user.id)
    await callback.answer()


@router.callback_query(F.data == "book_restart")
async def cb_book_restart(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await _show_service_picker(callback.message.edit_text, state, callback.from_user.id)
    await callback.answer()


# ── Шаг 1: формат -> дни со свободными слотами ──────────────────────────

@router.callback_query(BookingForm.waiting_service, F.data.startswith("book_svc:"))
async def cb_book_service(callback: CallbackQuery, state: FSMContext):
    key = callback.data.split(":", 1)[1]
    svc = _service_by_key(key)
    if not svc:
        # Неизвестный/подделанный ключ формата — цена больше не идёт в
        # callback_data именно для защиты от подмены (см. брифа трек 4).
        await callback.answer("Формат недоступен", show_alert=True)
        await state.clear()
        return
    await state.update_data(service_key=key, service_price=svc["price"])

    slots = await _get_free_slots()
    if not slots:
        await callback.message.edit_text(
            BOOKING_NO_SLOTS_TEXT, parse_mode="HTML", reply_markup=_booking_coming_soon_keyboard(),
        )
        await callback.answer()
        return

    await callback.message.edit_text(
        "📅 <b>Выберите день:</b>",
        parse_mode="HTML",
        reply_markup=_day_picker_keyboard(slots, "book_day:", "book_restart"),
    )
    await state.set_state(BookingForm.waiting_slot)
    await callback.answer()


@router.callback_query(BookingForm.waiting_slot, F.data.startswith("book_day:"))
async def cb_book_day(callback: CallbackQuery):
    day = date.fromisoformat(callback.data.split(":", 1)[1])
    slots = await _get_free_slots()
    slots_for_day = [s for s in slots if s["dt"].date() == day]
    if not slots_for_day:
        await callback.answer("На этот день слотов уже не осталось", show_alert=True)
        return
    await callback.message.edit_text(
        f"📅 <b>{_ru_day_label(day)}</b>\n\nВыберите время:",
        parse_mode="HTML",
        reply_markup=_time_picker_keyboard(slots_for_day, "book_slot:", "book_day_back"),
    )
    await callback.answer()


@router.callback_query(BookingForm.waiting_slot, F.data == "book_day_back")
async def cb_book_day_back(callback: CallbackQuery):
    slots = await _get_free_slots()
    if not slots:
        await callback.message.edit_text(
            BOOKING_NO_SLOTS_TEXT, parse_mode="HTML", reply_markup=_booking_coming_soon_keyboard(),
        )
        await callback.answer()
        return
    await callback.message.edit_text(
        "📅 <b>Выберите день:</b>",
        parse_mode="HTML",
        reply_markup=_day_picker_keyboard(slots, "book_day:", "book_restart"),
    )
    await callback.answer()


def _phone_consent_keyboard() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(
        text="✅ Согласен(на) передать номер телефона",
        callback_data="book_phone_consent:accept",
    ))
    b.row(InlineKeyboardButton(text="◀️ Главное меню", callback_data="menu:main"))
    return b.as_markup()


@router.callback_query(BookingForm.waiting_slot, F.data.startswith("book_slot:"))
async def cb_book_slot(callback: CallbackQuery, state: FSMContext):
    slot_id = int(callback.data.split(":")[1])
    await state.update_data(slot_id=slot_id)

    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT slot_dt FROM booking_slots WHERE id=$1 AND is_booked=FALSE", slot_id,
        )
    if not row:
        await callback.answer("Этот слот уже заняли — выберите другое время", show_alert=True)
        return

    dt: datetime = row["slot_dt"]
    await state.update_data(slot_dt=dt.isoformat())

    # 152-ФЗ: телефон — самые чувствительные данные в этом FSM, отдельное
    # подтверждение перед тем, как бот вообще примет ввод номера.
    await callback.message.edit_text(
        f"✅ Время: <b>{_ru_dt_label(dt)} МСК</b>\n\n"
        "📞 Для подтверждения записи нужен ваш номер телефона — мы свяжемся "
        "с вами по нему. Подтвердите согласие на передачу номера:",
        parse_mode="HTML",
        reply_markup=_phone_consent_keyboard(),
    )
    await state.set_state(BookingForm.waiting_phone_consent)
    await callback.answer()


def _phone_entry_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 Поделиться номером", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,  # клиент может и написать текстом — защита PR #52 это обрабатывает
    )


@router.callback_query(BookingForm.waiting_phone_consent, F.data == "book_phone_consent:accept")
async def cb_book_phone_consent(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "📞 Укажите ваш <b>телефон</b> для подтверждения:",
        parse_mode="HTML",
    )
    await callback.message.answer(
        "Нажмите кнопку ниже, чтобы поделиться номером, или напишите его текстом.",
        reply_markup=_phone_entry_keyboard(),
    )
    await state.set_state(BookingForm.waiting_contact)
    await callback.answer()


@router.message(BookingForm.waiting_contact)
async def process_contact(message: Message, state: FSMContext, bot: Bot):
    # Кнопка "Поделиться номером" шлёт message.contact; запасной путь — текст.
    own_phone = _own_contact_phone(message)
    phone = (own_phone if own_phone else (message.text or "")).strip()

    data = await state.get_data()

    # Сначала — анкета (слот/услуга): если её данные потеряны, телефон уже
    # не имеет смысла проверять отдельно, это одна и та же проблема.
    missing = _missing_booking_fields(data)
    if missing:
        log.warning(
            "process_contact: в анкете записи не хватает полей (user_id=%s): %s",
            message.from_user.id, ", ".join(missing),
        )
        await message.answer(BOOKING_RETRY_TEXT, parse_mode="HTML", reply_markup=_booking_restart_keyboard())
        await state.clear()
        return

    # Анкета цела, но вместо номера пришло не текстовое сообщение (или
    # пустая строка/пробелы, или чужой контакт) — просим прислать телефон
    # ещё раз и не трогаем ни state, ни уже выбранные слот/услугу.
    if not phone:
        await message.answer(BOOKING_PHONE_AS_TEXT, parse_mode="HTML", reply_markup=_phone_entry_keyboard())
        return

    slot_id   = data["slot_id"]
    slot_dt   = data["slot_dt"]
    svc_key   = data["service_key"]
    svc_price = data["service_price"]
    svc = _service_by_key(svc_key)
    svc_name = svc["label"] if svc else svc_key
    duration_min = svc["duration_min"] if svc else 60
    duration_h = duration_min / 60

    pool = await get_pool()
    booking_id = None
    async with pool.acquire() as conn, conn.transaction():
        # Атомарный захват слота: пустой результат -> слот уже заняли
        # (кто-то успел раньше), пока клиент вводил номер.
        claimed_id = await conn.fetchval(
            "UPDATE booking_slots SET is_booked=TRUE WHERE id=$1 AND is_booked=FALSE RETURNING id",
            slot_id,
        )
        if claimed_id is not None:
            booking_id = await conn.fetchval(
                """INSERT INTO bookings (telegram_id, slot_id, service_key, service_name, service_price, phone)
                   VALUES ($1,$2,$3,$4,$5,$6) RETURNING id""",
                message.from_user.id, slot_id, svc_key, svc_name, svc_price, phone,
            )

    if booking_id is None:
        await message.answer(
            "😔 Этот слот уже заняли, пока вы вводили номер. Пожалуйста, выберите другое время.",
            parse_mode="HTML",
            reply_markup=_booking_restart_keyboard(),
        )
        await state.clear()
        return

    # Reply-keyboard "Поделиться номером" была показана независимо от того,
    # пришёл телефон кнопкой или текстом — убираем её явно перед подтверждением.
    await message.answer("Номер получен ✅", reply_markup=ReplyKeyboardRemove())

    dt = datetime.fromisoformat(slot_dt)

    ics_description = (
        f"Услуга: {svc_name}\n"
        f"Телефон: {phone}\n"
        f"Дизайнер: {DESIGNER_NAME}"
    )
    gcal_url = build_google_calendar_url(
        title=f"Консультация ВашСад — {svc_name}",
        start_dt=dt,
        duration_hours=duration_h,
        location="Онлайн (Telegram)",
        description=ics_description,
    )

    builder_confirm = InlineKeyboardBuilder()
    builder_confirm.row(InlineKeyboardButton(text="📅 Добавить в Google Calendar", url=gcal_url))
    builder_confirm.row(InlineKeyboardButton(text="❌ Отменить запись", callback_data=f"book_cancel:{booking_id}"))
    builder_confirm.row(InlineKeyboardButton(text="🔁 Записаться заново", callback_data="book_restart"))
    # Перенос из подтверждения клиенту не делаем — упрощение по брифу: вместо
    # "Перенести" клиент может отменить и записаться заново (кнопка выше).
    # Полноценный перенос реализован на стороне сотрудника (badm_resched:*).

    await message.answer(
        f"🎉 <b>Запись подтверждена!</b>\n\n"
        f"📅 {_ru_dt_label(dt)} МСК\n"
        f"🛎 {svc_name}\n"
        f"📞 {phone}\n\n"
        f"Мы свяжемся с вами для подтверждения. До встречи! 🌿",
        parse_mode="HTML",
        reply_markup=builder_confirm.as_markup(),
    )

    # Отправляем ICS-файл
    try:
        ics_bytes = generate_ics(
            title=f"Консультация ВашСад — {svc_name}",
            start_dt=dt,
            duration_hours=duration_h,
            location="Онлайн (Telegram)",
            description=ics_description,
            organizer_email="info@vashsad.ru",
        )
        await message.answer_document(
            BufferedInputFile(ics_bytes, filename="консультация.ics"),
            caption="📎 Файл для добавления в любой календарь (iCal, Apple Calendar, Outlook)",
        )
    except Exception as e:
        log.warning("Ошибка генерации ICS: %s", e)

    # Планируем напоминания за 24ч и 1ч — явно в Europe/Moscow (см. докстринг
    # модуля): не полагаемся на дефолтный timezone планировщика неявно.
    try:
        from services.scheduler import schedule_booking_reminders
        await schedule_booking_reminders(bot, booking_id, dt)
    except Exception as e:
        log.warning("Ошибка планирования напоминаний: %s", e)

    user = message.from_user
    notify_kb = InlineKeyboardBuilder()
    if user.username:
        notify_kb.row(InlineKeyboardButton(text="✉️ Написать клиенту", url=f"https://t.me/{user.username}"))
    notify_kb.row(InlineKeyboardButton(text="📞 Позвонить", callback_data=f"badm_phone:{booking_id}"))

    for recipient_id in _booking_recipient_ids():
        try:
            await bot.send_message(
                recipient_id,
                f"📅 <b>Новая запись!</b>\n\n"
                f"👤 {html.escape(user.first_name or '')} (@{user.username or '—'})\n"
                f"🛎 {svc_name} — {svc_price:,} ₽\n"
                f"📅 {_ru_dt_label(dt)} МСК\n"
                f"📞 {phone}",
                parse_mode="HTML",
                reply_markup=notify_kb.as_markup(),
            )
        except Exception as e:
            log.warning("Уведомление о записи получателю %s: %s", recipient_id, e)

    await state.clear()


@router.callback_query(F.data.startswith("book_cancel:"))
async def cb_book_cancel(callback: CallbackQuery, bot: Bot):
    booking_id = int(callback.data.split(":")[1])
    pool = await get_pool()
    async with pool.acquire() as conn, conn.transaction():
        row = await conn.fetchrow(
            "SELECT telegram_id, slot_id, service_name FROM bookings WHERE id=$1 AND status='confirmed'",
            booking_id,
        )
        if not row:
            await callback.answer("Эта запись уже недоступна.", show_alert=True)
            return
        if row["telegram_id"] != callback.from_user.id:
            await callback.answer("Нет доступа", show_alert=True)
            return
        await conn.execute("UPDATE bookings SET status='cancelled' WHERE id=$1", booking_id)
        await conn.execute("UPDATE booking_slots SET is_booked=FALSE WHERE id=$1", row["slot_id"])

    from services.scheduler import cancel_booking_reminders
    cancel_booking_reminders(booking_id)

    await callback.message.edit_text(
        "❌ Запись отменена. Будем рады видеть вас снова!",
        parse_mode="HTML",
        reply_markup=InlineKeyboardBuilder().row(
            InlineKeyboardButton(text="📅 Записаться заново", callback_data="book_restart"),
        ).row(
            InlineKeyboardButton(text="◀️ Главное меню", callback_data="menu:main"),
        ).as_markup(),
    )
    for recipient_id in _booking_recipient_ids():
        try:
            await bot.send_message(
                recipient_id,
                f"❌ Клиент отменил запись #{booking_id} ({row['service_name']}).",
            )
        except Exception as e:
            log.warning("Уведомление об отмене получателю %s: %s", recipient_id, e)
    await callback.answer()


LEAVE_REQUEST_PROMPT_TEXT = (
    "📝 Напишите одним сообщением, что хотите обсудить и когда вам удобно. "
    "Можно оставить телефон."
)

LEAVE_REQUEST_RETRY_TEXT = (
    "📝 Пожалуйста, напишите текстом, что вас интересует, или поделитесь "
    "номером кнопкой ниже."
)


def _leave_request_cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardBuilder().row(
        InlineKeyboardButton(text="◀️ Отмена", callback_data="book_leave_cancel"),
    ).as_markup()


@router.callback_query(F.data == "book_leave_request")
async def cb_book_leave_request(callback: CallbackQuery, state: FSMContext):
    """Нет слотов / запись ещё не открыта — свободная заявка (без новой таблицы,
    решение по брифу: если можно обойтись без схемы — обойтись); сохраняем
    service_key в data, если клиент успел его выбрать."""
    await callback.message.edit_text(
        LEAVE_REQUEST_PROMPT_TEXT, parse_mode="HTML", reply_markup=_leave_request_cancel_keyboard(),
    )
    await callback.message.answer(
        "Нажмите кнопку ниже, чтобы поделиться номером, или напишите сообщение текстом.",
        reply_markup=_phone_entry_keyboard(),
    )
    await state.set_state(BookingRequest.waiting_text)
    await callback.answer()


@router.callback_query(BookingRequest.waiting_text, F.data == "book_leave_cancel")
async def cb_book_leave_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        BOOKING_COMING_SOON_TEXT if not BOOKING_OPEN_FOR_CLIENTS else BOOKING_NO_SLOTS_TEXT,
        parse_mode="HTML",
        reply_markup=_booking_coming_soon_keyboard(),
    )
    await callback.answer()


@router.message(BookingRequest.waiting_text)
async def process_leave_request(message: Message, state: FSMContext, bot: Bot):
    phone = _own_contact_phone(message)
    client_text = "" if phone else (message.text or "").strip()[:1000]

    if not phone and not client_text:
        await message.answer(
            LEAVE_REQUEST_RETRY_TEXT, parse_mode="HTML", reply_markup=_phone_entry_keyboard(),
        )
        return

    # Reply-keyboard "Поделиться номером" была показана в любом случае —
    # убираем её явно перед подтверждением (как и в основном сценарии записи).
    await message.answer("Информация получена ✅", reply_markup=ReplyKeyboardRemove())

    data = await state.get_data()
    svc = _service_by_key(data.get("service_key", ""))
    user = message.from_user
    username_label = f"@{user.username}" if user.username else "нет username"

    staff_lines = [
        "📝 <b>Заявка на запись (текст)</b>\n",
        f"👤 {html.escape(user.first_name or '')} ({username_label})",
        f"🆔 <code>{user.id}</code>",
    ]
    if svc:
        staff_lines.append(f"🛎 Формат: {svc['label']}")
    if client_text:
        staff_lines.append(f"💬 {html.escape(client_text)}")
    if phone:
        staff_lines.append(f"📞 {phone}")
    staff_text = "\n".join(staff_lines)

    kb = InlineKeyboardBuilder()
    contact_url = f"https://t.me/{user.username}" if user.username else f"tg://user?id={user.id}"
    kb.row(InlineKeyboardButton(text="✉️ Написать клиенту", url=contact_url))

    sent_any = False
    for recipient_id in _booking_recipient_ids():
        try:
            await bot.send_message(recipient_id, staff_text, parse_mode="HTML", reply_markup=kb.as_markup())
            sent_any = True
        except Exception as e:
            log.warning("Уведомление о заявке (текст) получателю %s: %s", recipient_id, e)

    await state.clear()
    if sent_any:
        await message.answer(
            "✅ Заявка принята! Мы свяжемся с вами, чтобы подобрать время.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardBuilder().row(
                InlineKeyboardButton(text="◀️ Главное меню", callback_data="menu:main"),
            ).as_markup(),
        )
    else:
        log.error("process_leave_request: ни одному получателю не удалось отправить заявку (user_id=%s)", user.id)
        await message.answer(
            "😔 Не получилось отправить заявку. Пожалуйста, напишите нам напрямую.",
            parse_mode="HTML",
            reply_markup=_booking_coming_soon_keyboard(),
        )


# ── Создание слотов (переиспользуется ручной кнопкой и автогенерацией) ────

async def _generate_week_slots(start_from: datetime | None = None) -> int:
    """Создаёт слоты по расписанию из конфига (BOOKING_AUTOSLOTS_*) на 7 дней
    вперёд от start_from (по умолчанию — сейчас по Москве). Идемпотентно
    (slot_dt UNIQUE, ON CONFLICT DO NOTHING). Возвращает число РЕАЛЬНО
    добавленных строк (не попыток — раньше счётчик считал попытки)."""
    now = start_from or _moscow_now_naive()
    added = 0
    pool = await get_pool()
    async with pool.acquire() as conn:
        for d in range(1, 8):
            day = now + timedelta(days=d)
            if day.weekday() not in BOOKING_AUTOSLOTS_WEEKDAYS:
                continue
            for hour in BOOKING_AUTOSLOTS_HOURS:
                slot_dt = day.replace(hour=hour, minute=0, second=0, microsecond=0)
                try:
                    inserted_id = await conn.fetchval(
                        """INSERT INTO booking_slots (slot_dt, duration_min) VALUES ($1, $2)
                           ON CONFLICT DO NOTHING RETURNING id""",
                        slot_dt, BOOKING_AUTOSLOTS_DURATION_MIN,
                    )
                    if inserted_id is not None:
                        added += 1
                except Exception as e:
                    log.warning("Слот %s не добавлен: %s", slot_dt, e)
    return added


async def generate_week_slots_job() -> None:
    """Обёртка для еженедельной джобы планировщика (services/scheduler.py),
    включается только если BOOKING_AUTOSLOTS_ENABLED=true."""
    added = await _generate_week_slots()
    log.info("Автогенерация слотов: добавлено %d", added)


# ── /slots — запасной вход (команда), теперь по общей проверке доступа ────

@router.message(Command("slots"))
async def cmd_slots(message: Message):
    if not _is_booking_staff(message.from_user.id):
        return
    await message.answer(
        "⚙️ <b>Управление записью</b>",
        parse_mode="HTML",
        reply_markup=_booking_admin_keyboard(),
    )


@router.message(Command("booking_admin"))
async def cmd_booking_admin(message: Message):
    await cmd_slots(message)


@router.callback_query(F.data == "menu:booking_admin")
async def cb_menu_booking_admin(callback: CallbackQuery):
    if not _is_booking_staff(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    await callback.message.edit_text(
        "⚙️ <b>Управление записью</b>", parse_mode="HTML", reply_markup=_booking_admin_keyboard(),
    )
    await callback.answer()


def _booking_admin_keyboard() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="➕ Слоты на неделю", callback_data="slots:add_week"))
    b.row(InlineKeyboardButton(text="➕ Слот на день/время", callback_data="badm_addslot"))
    b.row(InlineKeyboardButton(text="🔒 Закрыть слот", callback_data="badm_close_list"))
    b.row(InlineKeyboardButton(text="📋 Ближайшие слоты", callback_data="slots:list"))
    b.row(InlineKeyboardButton(text="📑 Записи", callback_data="badm_bookings"))
    return b.as_markup()


@router.callback_query(F.data == "slots:add_week")
async def cb_add_week_slots(callback: CallbackQuery):
    if not _is_booking_staff(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    added = await _generate_week_slots()
    await callback.answer(f"Добавлено {added} слотов", show_alert=True)


@router.callback_query(F.data == "slots:list")
async def cb_list_slots(callback: CallbackQuery):
    if not _is_booking_staff(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT slot_dt, is_booked FROM booking_slots
               WHERE slot_dt > $1 ORDER BY slot_dt LIMIT 14""",
            _moscow_now_naive(),
        )
    if not rows:
        await callback.answer("Слотов нет", show_alert=True)
        return
    lines = [
        f"{'✅' if r['is_booked'] else '🟢'} {_ru_dt_label_short(r['slot_dt'])} МСК"
        for r in rows
    ]
    await callback.message.answer(
        "📅 <b>Слоты (ближайшие 14):</b>\n\n" + "\n".join(lines),
        parse_mode="HTML",
    )
    await callback.answer()


# ── Точечное добавление слота (день -> час, кнопками) ──────────────────

@router.callback_query(F.data == "badm_addslot")
async def cb_badm_addslot(callback: CallbackQuery):
    if not _is_booking_staff(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    today = _moscow_now_naive().date()
    b = InlineKeyboardBuilder()
    for i in range(1, MANUAL_SLOT_DAYS_AHEAD + 1):
        day = today + timedelta(days=i)
        b.row(InlineKeyboardButton(text=_ru_day_label(day), callback_data=f"badm_addslot_day:{day.isoformat()}"))
    b.row(InlineKeyboardButton(text="◀️ Назад", callback_data="menu:booking_admin"))
    await callback.message.edit_text(
        "➕ <b>На какой день добавить слот?</b>", parse_mode="HTML", reply_markup=b.as_markup(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("badm_addslot_day:"))
async def cb_badm_addslot_day(callback: CallbackQuery):
    if not _is_booking_staff(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    day_iso = callback.data.split(":", 1)[1]
    b = InlineKeyboardBuilder()
    for hour in MANUAL_SLOT_HOURS:
        b.button(text=f"{hour:02d}:00", callback_data=f"badm_addslot_time:{day_iso}:{hour}")
    b.adjust(3)
    b.row(InlineKeyboardButton(text="◀️ Другой день", callback_data="badm_addslot"))
    await callback.message.edit_text("➕ <b>Во сколько?</b>", parse_mode="HTML", reply_markup=b.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("badm_addslot_time:"))
async def cb_badm_addslot_time(callback: CallbackQuery):
    if not _is_booking_staff(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    _, day_iso, hour_s = callback.data.split(":")
    day = date.fromisoformat(day_iso)
    slot_dt = datetime(day.year, day.month, day.day, int(hour_s))
    pool = await get_pool()
    async with pool.acquire() as conn:
        inserted_id = await conn.fetchval(
            """INSERT INTO booking_slots (slot_dt, duration_min) VALUES ($1, $2)
               ON CONFLICT DO NOTHING RETURNING id""",
            slot_dt, BOOKING_AUTOSLOTS_DURATION_MIN,
        )
    if inserted_id is not None:
        await callback.answer(f"Слот {_ru_dt_label_short(slot_dt)} МСК добавлен", show_alert=True)
    else:
        await callback.answer("Такой слот уже существует", show_alert=True)


# ── Закрытие слота ──────────────────────────────────────────────────────

@router.callback_query(F.data == "badm_close_list")
async def cb_badm_close_list(callback: CallbackQuery):
    if not _is_booking_staff(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    slots = await _get_free_slots()
    if not slots:
        await callback.answer("Свободных слотов нет", show_alert=True)
        return
    await callback.message.edit_text(
        "🔒 <b>Какой день?</b>", parse_mode="HTML",
        reply_markup=_day_picker_keyboard(slots, "badm_close_day:", "menu:booking_admin"),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("badm_close_day:"))
async def cb_badm_close_day(callback: CallbackQuery):
    if not _is_booking_staff(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    day = date.fromisoformat(callback.data.split(":", 1)[1])
    slots = await _get_free_slots()
    slots_for_day = [s for s in slots if s["dt"].date() == day]
    if not slots_for_day:
        await callback.answer("На этот день слотов уже не осталось", show_alert=True)
        return
    await callback.message.edit_text(
        f"🔒 <b>{_ru_day_label(day)}</b> — выберите слот для закрытия:",
        parse_mode="HTML",
        reply_markup=_time_picker_keyboard(slots_for_day, "badm_close:", "badm_close_list"),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("badm_close:"))
async def cb_badm_close(callback: CallbackQuery):
    if not _is_booking_staff(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    slot_id = int(callback.data.split(":")[1])
    pool = await get_pool()
    async with pool.acquire() as conn:
        # Закрытие использует тот же флаг is_booked, что и обычное бронирование
        # (отдельного статуса "закрыт" в схеме нет — не добавляю новую колонку).
        closed_id = await conn.fetchval(
            "UPDATE booking_slots SET is_booked=TRUE WHERE id=$1 AND is_booked=FALSE RETURNING id",
            slot_id,
        )
    await callback.answer("Слот закрыт" if closed_id is not None else "Слот уже занят/закрыт", show_alert=True)


# ── Список записей, отмена и перенос (сотрудник) ───────────────────────

@router.callback_query(F.data == "badm_bookings")
async def cb_badm_bookings(callback: CallbackQuery):
    if not _is_booking_staff(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT b.id, b.service_name, b.phone, s.slot_dt
               FROM bookings b JOIN booking_slots s ON s.id = b.slot_id
               WHERE b.status = 'confirmed' AND s.slot_dt > $1
               ORDER BY s.slot_dt LIMIT 10""",
            _moscow_now_naive(),
        )
    if not rows:
        await callback.answer("Ближайших записей нет", show_alert=True)
        return
    b = InlineKeyboardBuilder()
    lines = ["📑 <b>Ближайшие записи:</b>\n"]
    for r in rows:
        lines.append(f"#{r['id']} · {_ru_dt_label_short(r['slot_dt'])} МСК · {r['service_name']}")
        b.row(
            InlineKeyboardButton(text=f"❌ Отменить #{r['id']}", callback_data=f"badm_cancel:{r['id']}"),
            InlineKeyboardButton(text=f"🔁 Перенести #{r['id']}", callback_data=f"badm_resched:{r['id']}"),
        )
    b.row(InlineKeyboardButton(text="◀️ Назад", callback_data="menu:booking_admin"))
    await callback.message.edit_text("\n".join(lines), parse_mode="HTML", reply_markup=b.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("badm_cancel:"))
async def cb_badm_cancel(callback: CallbackQuery, bot: Bot):
    if not _is_booking_staff(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    booking_id = int(callback.data.split(":")[1])
    pool = await get_pool()
    async with pool.acquire() as conn, conn.transaction():
        row = await conn.fetchrow(
            "SELECT telegram_id, slot_id FROM bookings WHERE id=$1 AND status='confirmed'", booking_id,
        )
        if not row:
            await callback.answer("Запись уже недоступна", show_alert=True)
            return
        await conn.execute("UPDATE bookings SET status='cancelled' WHERE id=$1", booking_id)
        await conn.execute("UPDATE booking_slots SET is_booked=FALSE WHERE id=$1", row["slot_id"])

    from services.scheduler import cancel_booking_reminders
    cancel_booking_reminders(booking_id)
    try:
        await bot.send_message(
            row["telegram_id"],
            "❌ К сожалению, ваша запись на консультацию отменена. Напишите нам, чтобы выбрать новое время.",
        )
    except Exception as e:
        log.warning("Уведомление клиенту об отмене (booking_id=%s): %s", booking_id, e)
    await callback.answer("Запись отменена, клиент уведомлён", show_alert=True)


@router.callback_query(F.data.startswith("badm_resched:"))
async def cb_badm_resched(callback: CallbackQuery):
    if not _is_booking_staff(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    booking_id = callback.data.split(":")[1]
    slots = await _get_free_slots()
    if not slots:
        await callback.answer("Свободных слотов для переноса нет", show_alert=True)
        return
    await callback.message.edit_text(
        f"🔁 <b>Перенос записи #{booking_id}</b> — выберите день:",
        parse_mode="HTML",
        reply_markup=_day_picker_keyboard(slots, f"badm_rday:{booking_id}:", "badm_bookings"),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("badm_rday:"))
async def cb_badm_rday(callback: CallbackQuery):
    if not _is_booking_staff(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    _, booking_id, day_iso = callback.data.split(":")
    day = date.fromisoformat(day_iso)
    slots = await _get_free_slots()
    slots_for_day = [s for s in slots if s["dt"].date() == day]
    if not slots_for_day:
        await callback.answer("На этот день слотов уже не осталось", show_alert=True)
        return
    await callback.message.edit_text(
        f"🔁 <b>Перенос записи #{booking_id}</b> — {_ru_day_label(day)}:",
        parse_mode="HTML",
        reply_markup=_time_picker_keyboard(
            slots_for_day, f"badm_resched_pick:{booking_id}:", f"badm_resched:{booking_id}",
        ),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("badm_resched_pick:"))
async def cb_badm_resched_pick(callback: CallbackQuery, bot: Bot):
    if not _is_booking_staff(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    _, booking_id_s, new_slot_id_s = callback.data.split(":")
    booking_id, new_slot_id = int(booking_id_s), int(new_slot_id_s)

    pool = await get_pool()
    new_booking_id = None
    new_dt = None
    old_telegram_id = None
    async with pool.acquire() as conn, conn.transaction():
        old = await conn.fetchrow(
            """SELECT telegram_id, slot_id, service_key, service_name, service_price, phone
               FROM bookings WHERE id=$1 AND status='confirmed'""",
            booking_id,
        )
        if not old:
            await callback.answer("Запись уже недоступна", show_alert=True)
            return

        # Атомарный захват нового слота: пустой результат -> его успели
        # занять, пока сотрудник выбирал время переноса.
        claimed_id = await conn.fetchval(
            "UPDATE booking_slots SET is_booked=TRUE WHERE id=$1 AND is_booked=FALSE RETURNING id",
            new_slot_id,
        )
        if claimed_id is None:
            await callback.answer("Этот слот уже занят, выберите другой", show_alert=True)
            return
        new_dt = await conn.fetchval("SELECT slot_dt FROM booking_slots WHERE id=$1", new_slot_id)

        await conn.execute("UPDATE bookings SET status='rescheduled' WHERE id=$1", booking_id)
        await conn.execute("UPDATE booking_slots SET is_booked=FALSE WHERE id=$1", old["slot_id"])
        new_booking_id = await conn.fetchval(
            """INSERT INTO bookings (telegram_id, slot_id, service_key, service_name, service_price, phone)
               VALUES ($1,$2,$3,$4,$5,$6) RETURNING id""",
            old["telegram_id"], new_slot_id, old["service_key"], old["service_name"],
            old["service_price"], old["phone"],
        )
        old_telegram_id = old["telegram_id"]

    from services.scheduler import cancel_booking_reminders, schedule_booking_reminders
    cancel_booking_reminders(booking_id)
    try:
        await schedule_booking_reminders(bot, new_booking_id, new_dt)
    except Exception as e:
        log.warning("Ошибка планирования напоминаний после переноса (booking_id=%s): %s", new_booking_id, e)

    try:
        await bot.send_message(
            old_telegram_id,
            f"🔁 Ваша запись перенесена на {_ru_dt_label(new_dt)} МСК.",
        )
    except Exception as e:
        log.warning("Уведомление клиенту о переносе (booking_id=%s): %s", booking_id, e)
    await callback.answer(
        f"Перенесено на {_ru_dt_label_short(new_dt)} МСК (запись #{new_booking_id})", show_alert=True,
    )


@router.callback_query(F.data.startswith("badm_phone:"))
async def cb_badm_phone(callback: CallbackQuery):
    if not _is_booking_staff(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    booking_id = int(callback.data.split(":")[1])
    pool = await get_pool()
    async with pool.acquire() as conn:
        phone = await conn.fetchval("SELECT phone FROM bookings WHERE id=$1", booking_id)
    await callback.answer(phone or "Телефон не найден", show_alert=True)


async def create_booking_tables():
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS booking_slots (
            id           SERIAL PRIMARY KEY,
            slot_dt      TIMESTAMP UNIQUE,
            duration_min INTEGER DEFAULT 60,
            is_booked    BOOLEAN DEFAULT FALSE,
            created_at   TIMESTAMP DEFAULT NOW()
        );
        CREATE TABLE IF NOT EXISTS bookings (
            id           SERIAL PRIMARY KEY,
            telegram_id  BIGINT REFERENCES users(telegram_id),
            slot_id      INTEGER REFERENCES booking_slots(id),
            service_key  VARCHAR(32),
            service_name VARCHAR(128),
            service_price INTEGER,
            phone        VARCHAR(32),
            status       VARCHAR(32) DEFAULT 'confirmed',
            created_at   TIMESTAMP DEFAULT NOW()
        );
        """)
