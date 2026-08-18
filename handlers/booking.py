"""Фаза 1: Запись на консультацию — FSM с выбором слота"""
import logging
from datetime import datetime, timedelta
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, BufferedInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import DESIGNER_TELEGRAM_ID, DESIGNER_NAME
from services.database import get_pool
from services.calendar_service import generate_ics, build_google_calendar_url

router = Router()
log = logging.getLogger(__name__)


class BookingForm(StatesGroup):
    waiting_service = State()
    waiting_slot    = State()
    waiting_contact = State()


BOOKING_SERVICES = [
    ("Онлайн-консультация 60 мин", "consultation", 2500),
    ("Разбор участка по фото",     "photo_review",  1500),
    ("Стратегия сада",             "strategy",      3900),
]


async def _get_free_slots(days_ahead: int = 14) -> list[dict]:
    """Возвращает свободные слоты на ближайшие N дней."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT id, slot_dt, duration_min FROM booking_slots
               WHERE slot_dt > NOW() AND is_booked = FALSE
               ORDER BY slot_dt LIMIT 20"""
        )
    return [{"id": r["id"], "dt": r["slot_dt"], "dur": r["duration_min"]} for r in rows]


@router.message(Command("book"))
async def cmd_book(message: Message, state: FSMContext):
    builder = InlineKeyboardBuilder()
    for label, key, price in BOOKING_SERVICES:
        builder.row(InlineKeyboardButton(
            text=label,
            callback_data=f"book_svc:{key}:{price}",
        ))
    builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="menu:main"))
    await message.answer(
        "📅 <b>Запись на консультацию</b>\n\nВыберите формат:",
        parse_mode="HTML",
        reply_markup=builder.as_markup(),
    )
    await state.set_state(BookingForm.waiting_service)


@router.callback_query(BookingForm.waiting_service, F.data.startswith("book_svc:"))
async def cb_book_service(callback: CallbackQuery, state: FSMContext):
    _, key, price = callback.data.split(":")
    await state.update_data(service_key=key, service_price=int(price))

    slots = await _get_free_slots()
    if not slots:
        await callback.message.edit_text(
            "😔 <b>Свободных слотов нет</b>\n\n"
            "Напишите нам, и мы подберём удобное время вручную.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardBuilder().row(
                InlineKeyboardButton(text="◀️ Назад", callback_data="menu:main")
            ).as_markup(),
        )
        await state.clear()
        await callback.answer()
        return

    builder = InlineKeyboardBuilder()
    for slot in slots[:8]:
        dt: datetime = slot["dt"]
        label = dt.strftime("%d %b, %H:%M")
        builder.button(text=label, callback_data=f"book_slot:{slot['id']}")
    builder.adjust(2)
    builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="menu:main"))

    await callback.message.edit_text(
        "📅 <b>Выберите удобное время:</b>",
        parse_mode="HTML",
        reply_markup=builder.as_markup(),
    )
    await state.set_state(BookingForm.waiting_slot)
    await callback.answer()


@router.callback_query(BookingForm.waiting_slot, F.data.startswith("book_slot:"))
async def cb_book_slot(callback: CallbackQuery, state: FSMContext):
    slot_id = int(callback.data.split(":")[1])
    await state.update_data(slot_id=slot_id)

    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT slot_dt FROM booking_slots WHERE id=$1", slot_id)

    dt: datetime = row["slot_dt"]
    await state.update_data(slot_dt=dt.isoformat())

    await callback.message.edit_text(
        f"✅ Время: <b>{dt.strftime('%d %b в %H:%M')}</b>\n\n"
        "📞 Укажите ваш <b>телефон</b> для подтверждения:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardBuilder().row(
            InlineKeyboardButton(text="◀️ Отмена", callback_data="menu:main")
        ).as_markup(),
    )
    await state.set_state(BookingForm.waiting_contact)
    await callback.answer()


@router.message(BookingForm.waiting_contact)
async def process_contact(message: Message, state: FSMContext, bot: Bot):
    phone = message.text.strip()
    data  = await state.get_data()
    slot_id   = data["slot_id"]
    slot_dt   = data["slot_dt"]
    svc_key   = data["service_key"]
    svc_price = data["service_price"]
    svc_name  = next((l for l, k, _ in BOOKING_SERVICES if k == svc_key), svc_key)

    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO bookings (telegram_id, slot_id, service_key, service_name, service_price, phone)
               VALUES ($1,$2,$3,$4,$5,$6)""",
            message.from_user.id, slot_id, svc_key, svc_name, svc_price, phone,
        )
        await conn.execute("UPDATE booking_slots SET is_booked=TRUE WHERE id=$1", slot_id)

    dt = datetime.fromisoformat(slot_dt)

    # Определяем продолжительность услуги
    duration_map = {"consultation": 1.0, "photo_review": 0.5, "strategy": 1.5}
    duration_h = duration_map.get(svc_key, 1.0)

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

    builder_gcal = InlineKeyboardBuilder()
    builder_gcal.row(InlineKeyboardButton(
        text="📅 Добавить в Google Calendar",
        url=gcal_url,
    ))

    await message.answer(
        f"🎉 <b>Запись подтверждена!</b>\n\n"
        f"📅 {dt.strftime('%d %b в %H:%M')}\n"
        f"🛎 {svc_name}\n"
        f"📞 {phone}\n\n"
        f"Дизайнер свяжется с вами для подтверждения. До встречи! 🌿",
        parse_mode="HTML",
        reply_markup=builder_gcal.as_markup(),
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

    # Планируем напоминания за 24ч и 1ч
    try:
        from services.scheduler import schedule_booking_reminders
        # Получаем ID только что созданного booking
        pool = await get_pool()
        async with pool.acquire() as conn:
            bid = await conn.fetchval(
                "SELECT id FROM bookings WHERE telegram_id=$1 AND slot_id=$2 ORDER BY created_at DESC LIMIT 1",
                message.from_user.id, slot_id,
            )
        if bid:
            await schedule_booking_reminders(bot, message.from_user.id, bid, dt)
    except Exception as e:
        log.warning("Ошибка планирования напоминаний: %s", e)

    if DESIGNER_TELEGRAM_ID:
        try:
            user = message.from_user
            await bot.send_message(
                DESIGNER_TELEGRAM_ID,
                f"📅 <b>Новая запись!</b>\n\n"
                f"👤 {user.first_name} (@{user.username or '—'})\n"
                f"🛎 {svc_name} — {svc_price:,} ₽\n"
                f"📅 {dt.strftime('%d %b в %H:%M')}\n"
                f"📞 {phone}",
                parse_mode="HTML",
            )
        except Exception as e:
            log.warning("Уведомление дизайнеру: %s", e)

    await state.clear()


@router.message(Command("slots"))
async def cmd_slots(message: Message):
    """Управление слотами — только для дизайнера."""
    if message.from_user.id != DESIGNER_TELEGRAM_ID:
        return
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="➕ Добавить слоты на неделю", callback_data="slots:add_week"))
    builder.row(InlineKeyboardButton(text="📋 Показать слоты", callback_data="slots:list"))
    await message.answer(
        "📅 <b>Управление слотами</b>",
        parse_mode="HTML",
        reply_markup=builder.as_markup(),
    )


@router.callback_query(F.data == "slots:add_week")
async def cb_add_week_slots(callback: CallbackQuery):
    if callback.from_user.id != DESIGNER_TELEGRAM_ID:
        await callback.answer("Нет доступа", show_alert=True)
        return
    # Добавляем слоты Пн–Пт 10:00 и 14:00 на следующие 7 дней
    now = datetime.now()
    added = 0
    pool = await get_pool()
    async with pool.acquire() as conn:
        for d in range(1, 8):
            dt = now + timedelta(days=d)
            if dt.weekday() >= 5:  # пропускаем выходные
                continue
            for hour in (10, 14):
                slot_dt = dt.replace(hour=hour, minute=0, second=0, microsecond=0)
                try:
                    await conn.execute(
                        "INSERT INTO booking_slots (slot_dt, duration_min) VALUES ($1, 60) ON CONFLICT DO NOTHING",
                        slot_dt,
                    )
                    added += 1
                except Exception:
                    pass
    await callback.answer(f"Добавлено {added} слотов", show_alert=True)


@router.callback_query(F.data == "slots:list")
async def cb_list_slots(callback: CallbackQuery):
    if callback.from_user.id != DESIGNER_TELEGRAM_ID:
        await callback.answer("Нет доступа", show_alert=True)
        return
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT slot_dt, is_booked FROM booking_slots
               WHERE slot_dt > NOW() ORDER BY slot_dt LIMIT 14"""
        )
    if not rows:
        await callback.answer("Слотов нет", show_alert=True)
        return
    lines = [
        f"{'✅' if r['is_booked'] else '🟢'} {r['slot_dt'].strftime('%d %b %H:%M')}"
        for r in rows
    ]
    await callback.message.answer(
        "📅 <b>Слоты (ближайшие 14):</b>\n\n" + "\n".join(lines),
        parse_mode="HTML",
    )
    await callback.answer()


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
