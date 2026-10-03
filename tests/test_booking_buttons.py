"""Запись на консультацию кнопками (докс-трек 2026-10-03): часовой пояс (МСК),
группировка слотов по дням, экран «нет слотов/скоро откроется», права доступа
сотрудника, уведомление нескольким получателям, идемпотентность автосоздания.
"""
from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from handlers import booking
from services import calendar_service


def _mock_pool():
    pool = MagicMock()
    conn = AsyncMock()
    pool.acquire = MagicMock(return_value=AsyncMock(
        __aenter__=AsyncMock(return_value=conn),
        __aexit__=AsyncMock(return_value=False),
    ))
    return pool, conn


def _make_message(text: str | None = None, user_id: int = 100000002) -> MagicMock:
    msg = MagicMock()
    msg.text = text
    msg.contact = None
    msg.from_user = SimpleNamespace(id=user_id, first_name="Клиент", username="client_u")
    msg.answer = AsyncMock()
    msg.answer_document = AsyncMock()
    return msg


def _make_callback(data: str, user_id: int = 100000002) -> MagicMock:
    cb = MagicMock()
    cb.data = data
    cb.from_user = SimpleNamespace(id=user_id, first_name="Клиент", username="client_u")
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.message.answer = AsyncMock()
    cb.answer = AsyncMock()
    return cb


def _make_state(data: dict | None = None) -> AsyncMock:
    state = AsyncMock()
    state.get_data = AsyncMock(return_value=dict(data or {}))
    state.update_data = AsyncMock()
    state.set_state = AsyncMock()
    state.clear = AsyncMock()
    return state


# ── Часовой пояс: slot_dt (naive) трактуется как МСК, не UTC ───────────────

def test_calendar_service_treats_naive_datetime_as_moscow_not_utc():
    """10:00 (naive, 'слот по Москве') должно лечь в ICS как 07:00Z — раньше
    (до этого трека) наивное время трактовалось как UTC напрямую, то есть
    10:00 оставалось 10:00Z — разъезд на 3 часа с тем, что видит клиент."""
    ics = calendar_service.generate_ics(
        title="Тест", start_dt=datetime(2026, 10, 10, 10, 0), duration_hours=1.0,
    )
    text = ics.decode("utf-8")
    assert "DTSTART:20261010T070000Z" in text, text


def test_build_google_calendar_url_treats_naive_as_moscow():
    url = calendar_service.build_google_calendar_url(
        title="Тест", start_dt=datetime(2026, 10, 10, 10, 0), duration_hours=1.0,
    )
    assert "20261010T070000Z" in url


def test_calendar_service_aware_datetime_passed_through():
    """aware datetime не трогаем интерпретацией — берём как есть и просто конвертируем в UTC."""
    from zoneinfo import ZoneInfo
    aware = datetime(2026, 10, 10, 10, 0, tzinfo=ZoneInfo("Europe/Moscow"))
    ics = calendar_service.generate_ics(title="Тест", start_dt=aware, duration_hours=1.0)
    assert b"DTSTART:20261010T070000Z" in ics


def test_moscow_now_naive_is_plain_naive_datetime():
    now = booking._moscow_now_naive()
    assert now.tzinfo is None


# ── Группировка слотов по дням ──────────────────────────────────────────

def test_group_slots_by_day():
    slots = [
        {"id": 1, "dt": datetime(2026, 10, 10, 10, 0), "dur": 60},
        {"id": 2, "dt": datetime(2026, 10, 10, 14, 0), "dur": 60},
        {"id": 3, "dt": datetime(2026, 10, 12, 10, 0), "dur": 60},
    ]
    groups = booking._group_slots_by_day(slots)
    assert list(groups.keys()) == [date(2026, 10, 10), date(2026, 10, 12)]
    assert len(groups[date(2026, 10, 10)]) == 2
    assert len(groups[date(2026, 10, 12)]) == 1


def test_ru_day_label_format():
    label = booking._ru_day_label(date(2026, 10, 10))  # суббота
    assert "Сб" in label and "10" in label and "окт" in label


# ── Экран «нет слотов» / «запись скоро откроется» ───────────────────────

@pytest.mark.asyncio
async def test_no_slots_screen_shows_contact_button_when_configured():
    callback = _make_callback("book_svc:consultation:2500")
    state = _make_state()
    with patch.object(booking, "_get_free_slots", AsyncMock(return_value=[])), \
         patch.object(booking, "BOOKING_CONTACT_URL", "https://t.me/vashsad_admin"):
        await booking.cb_book_service(callback, state)

    kb = callback.message.edit_text.await_args.kwargs["reply_markup"]
    buttons = [(b.text, b.url, b.callback_data) for row in kb.inline_keyboard for b in row]
    assert any(url == "https://t.me/vashsad_admin" for _, url, _ in buttons)
    assert any(cd == "book_leave_request" for _, _, cd in buttons)


@pytest.mark.asyncio
async def test_no_slots_screen_hides_contact_button_when_not_configured():
    callback = _make_callback("book_svc:consultation:2500")
    state = _make_state()
    with patch.object(booking, "_get_free_slots", AsyncMock(return_value=[])), \
         patch.object(booking, "BOOKING_CONTACT_URL", ""):
        await booking.cb_book_service(callback, state)

    kb = callback.message.edit_text.await_args.kwargs["reply_markup"]
    buttons = [(b.text, getattr(b, "url", None)) for row in kb.inline_keyboard for b in row]
    assert not any(url for _, url in buttons), "пустая/выдуманная ссылка не должна рисоваться"
    assert any("Написать" not in t for t, _ in buttons)  # кнопки "Написать" нет вовсе
    assert not any("Написать" in t for t, _ in buttons)


@pytest.mark.asyncio
async def test_booking_open_for_clients_false_shows_coming_soon():
    message = _make_message()
    state = _make_state()
    with patch.object(booking, "BOOKING_OPEN_FOR_CLIENTS", False):
        await booking.cmd_book(message, state)

    text = message.answer.await_args.args[0]
    assert "скоро откроется" in text.lower()
    state.clear.assert_awaited_once()  # не оставляем в waiting_service без доступных форматов


@pytest.mark.asyncio
async def test_booking_open_for_clients_true_shows_formats():
    message = _make_message()
    state = _make_state()
    with patch.object(booking, "BOOKING_OPEN_FOR_CLIENTS", True):
        await booking.cmd_book(message, state)

    text = message.answer.await_args.args[0]
    assert "выберите формат" in text.lower()
    state.set_state.assert_awaited_once_with(booking.BookingForm.waiting_service)


# ── Права на экран сотрудника ───────────────────────────────────────────

def test_is_booking_staff_designer_ids():
    with patch.object(booking, "DESIGNER_TELEGRAM_ID", 111), \
         patch.object(booking, "DESIGNER_TELEGRAM_ID_2", 222), \
         patch.object(booking, "BOOKING_RECIPIENT_IDS", []):
        assert booking._is_booking_staff(111) is True
        assert booking._is_booking_staff(222) is True
        assert booking._is_booking_staff(333) is False


def test_is_booking_staff_recipient_ids_union_with_designers():
    """BOOKING_RECIPIENT_IDS добавляется К designer-id, не заменяет их (Аня/Нелли +
    Beaver остаются с доступом, даже если RECIPIENT_IDS заполнен)."""
    with patch.object(booking, "DESIGNER_TELEGRAM_ID", 111), \
         patch.object(booking, "DESIGNER_TELEGRAM_ID_2", 0), \
         patch.object(booking, "BOOKING_RECIPIENT_IDS", [444, 555]):
        assert booking._is_booking_staff(111) is True   # designer всё ещё имеет доступ
        assert booking._is_booking_staff(444) is True
        assert booking._is_booking_staff(555) is True
        assert booking._is_booking_staff(666) is False  # посторонний


def test_booking_recipient_ids_fallback_to_designers_when_empty():
    with patch.object(booking, "DESIGNER_TELEGRAM_ID", 111), \
         patch.object(booking, "DESIGNER_TELEGRAM_ID_2", 222), \
         patch.object(booking, "BOOKING_RECIPIENT_IDS", []):
        assert sorted(booking._booking_recipient_ids()) == [111, 222]


def test_booking_recipient_ids_explicit_overrides_fallback():
    with patch.object(booking, "DESIGNER_TELEGRAM_ID", 111), \
         patch.object(booking, "DESIGNER_TELEGRAM_ID_2", 222), \
         patch.object(booking, "BOOKING_RECIPIENT_IDS", [444, 555]):
        assert booking._booking_recipient_ids() == [444, 555]


@pytest.mark.asyncio
async def test_cmd_slots_denies_stranger():
    message = _make_message(user_id=999)
    with patch.object(booking, "DESIGNER_TELEGRAM_ID", 111), \
         patch.object(booking, "DESIGNER_TELEGRAM_ID_2", 0), \
         patch.object(booking, "BOOKING_RECIPIENT_IDS", []):
        await booking.cmd_slots(message)
    message.answer.assert_not_called()


@pytest.mark.asyncio
async def test_cmd_slots_allows_staff():
    message = _make_message(user_id=111)
    with patch.object(booking, "DESIGNER_TELEGRAM_ID", 111), \
         patch.object(booking, "DESIGNER_TELEGRAM_ID_2", 0), \
         patch.object(booking, "BOOKING_RECIPIENT_IDS", []):
        await booking.cmd_slots(message)
    message.answer.assert_awaited_once()


# ── Уведомление нескольким получателям, сбой одного не ломает остальных ──

@pytest.mark.asyncio
async def test_notify_recipients_one_failure_does_not_block_others():
    state = _make_state({
        "slot_id": 7,
        "slot_dt": datetime(2026, 10, 10, 10, 0).isoformat(),
        "service_key": "consultation",
        "service_price": 2500,
    })
    message = _make_message(text="+7 900 000-00-00")
    bot = AsyncMock()

    async def _send_message(chat_id, *a, **kw):
        if chat_id == 222:
            raise RuntimeError("бот заблокирован получателем")
        return MagicMock()

    bot.send_message = AsyncMock(side_effect=_send_message)

    pool, conn = _mock_pool()
    conn.fetchrow = AsyncMock(return_value={"id": 7})
    conn.fetchval = AsyncMock(return_value=42)

    with patch.object(booking, "get_pool", AsyncMock(return_value=pool)), \
         patch.object(booking, "DESIGNER_TELEGRAM_ID", 111), \
         patch.object(booking, "DESIGNER_TELEGRAM_ID_2", 0), \
         patch.object(booking, "BOOKING_RECIPIENT_IDS", [111, 222, 333]), \
         patch.object(booking, "build_google_calendar_url", return_value="https://x"), \
         patch.object(booking, "generate_ics", return_value=b"X"), \
         patch("services.scheduler.schedule_booking_reminders", AsyncMock()):
        await booking.process_contact(message, state, bot)

    # Все три получателя получили попытку; у 222 — сбой, но 111 и 333 всё равно вызваны.
    recipient_ids = [c.args[0] for c in bot.send_message.await_args_list if c.args]
    assert 111 in recipient_ids
    assert 222 in recipient_ids
    assert 333 in recipient_ids


# ── Автогенерация слотов: идемпотентность и честный счётчик ─────────────

@pytest.mark.asyncio
async def test_generate_week_slots_counts_only_real_inserts():
    """Счётчик считает РЕАЛЬНО добавленные строки (RETURNING id -> не None),
    а не попытки — раньше считались попытки (added += 1 внутри try, даже если
    ON CONFLICT DO NOTHING ничего не вставил)."""
    pool, conn = _mock_pool()
    # Чередуем: первый insert в день успешен (id), второй - конфликт (None)
    conn.fetchval = AsyncMock(side_effect=[1, None] * 20)

    with patch.object(booking, "get_pool", AsyncMock(return_value=pool)), \
         patch.object(booking, "BOOKING_AUTOSLOTS_WEEKDAYS", [0, 1, 2, 3, 4]), \
         patch.object(booking, "BOOKING_AUTOSLOTS_HOURS", [10, 14]):
        added = await booking._generate_week_slots(start_from=datetime(2026, 10, 5))  # понедельник

    # По будням (Пн-Пт из 7 дней вперёд от понедельника — 5 будних дней) x 2 часа = 10
    # попыток; из них по чередованию 1/None половина реально вставлена.
    assert added == 5  # 10 попыток, каждая вторая None -> 5 реальных вставок
    assert conn.fetchval.await_count == 10


@pytest.mark.asyncio
async def test_generate_week_slots_idempotent_second_run_adds_zero():
    """Повторный вызов с тем же стартовым временем ничего не добавляет
    (ON CONFLICT DO NOTHING -> fetchval возвращает None на уже существующий slot_dt)."""
    pool, conn = _mock_pool()
    conn.fetchval = AsyncMock(return_value=None)  # все слоты "уже существуют"

    with patch.object(booking, "get_pool", AsyncMock(return_value=pool)), \
         patch.object(booking, "BOOKING_AUTOSLOTS_WEEKDAYS", [0, 1, 2, 3, 4]), \
         patch.object(booking, "BOOKING_AUTOSLOTS_HOURS", [10, 14]):
        added = await booking._generate_week_slots(start_from=datetime(2026, 10, 5))

    assert added == 0


@pytest.mark.asyncio
async def test_generate_week_slots_respects_configured_weekdays_and_hours():
    pool, conn = _mock_pool()
    conn.fetchval = AsyncMock(return_value=1)

    with patch.object(booking, "get_pool", AsyncMock(return_value=pool)), \
         patch.object(booking, "BOOKING_AUTOSLOTS_WEEKDAYS", [0]), \
         patch.object(booking, "BOOKING_AUTOSLOTS_HOURS", [9]):
        added = await booking._generate_week_slots(start_from=datetime(2026, 10, 5))  # понедельник

    # Ровно 1 понедельник в ближайшие 7 дней, 1 час в расписании -> 1 вставка.
    assert added == 1
    assert conn.fetchval.await_count == 1
