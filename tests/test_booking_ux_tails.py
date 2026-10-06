"""B2 (ночной бриф 05→06.10.2026): два хвоста из аудита.

(а) В выборе слота закрытый сотрудником слот неотличим от занятого клиентом —
клиент (или сотрудник в предпросмотре) видел одно и то же BOOKING_NO_SLOTS_TEXT,
когда свободных слотов в окне не было, независимо от причины.

(б) После "Отмена"/сбоя анкеты в process_contact остаётся reply-клавиатура
"Поделиться номером" — должна сниматься во всех ветках отмены, не только в
cb_book_leave_cancel (см. test_booking_tails.py, тест (в) — другая ветка).
"""
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.types import ReplyKeyboardRemove

from handlers import booking

FULL_DATA = {
    "slot_id": 7,
    "slot_dt": datetime(2026, 10, 10, 12, 0).isoformat(),
    "service_key": "consultation",
    "service_price": 2500,
}


def _mock_pool():
    pool = MagicMock()
    conn = AsyncMock()
    conn.transaction = MagicMock(return_value=AsyncMock(
        __aenter__=AsyncMock(return_value=None),
        __aexit__=AsyncMock(return_value=False),
    ))
    pool.acquire = MagicMock(return_value=AsyncMock(
        __aenter__=AsyncMock(return_value=conn),
        __aexit__=AsyncMock(return_value=False),
    ))
    return pool, conn


def _make_callback(data: str = "", user_id: int = 100000777) -> MagicMock:
    cb = MagicMock()
    cb.data = data
    cb.from_user = SimpleNamespace(id=user_id, first_name="Клиент", username="client_u")
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.message.answer = AsyncMock()
    cb.answer = AsyncMock()
    return cb


def _make_message(text: str | None = None, user_id: int = 100000777) -> MagicMock:
    msg = MagicMock()
    msg.text = text
    msg.contact = None
    msg.from_user = SimpleNamespace(id=user_id, first_name="Клиент", username="client_u")
    msg.answer = AsyncMock()
    return msg


def _make_state(data: dict) -> AsyncMock:
    state = AsyncMock()
    state.get_data = AsyncMock(return_value=dict(data))
    state.clear = AsyncMock()
    return state


# ── (а) различие "закрыт"/"занят"/"не выставлено" в сообщении о нуле слотов ─

@pytest.mark.asyncio
@pytest.mark.parametrize("booked,closed,expected_const", [
    (0, 0, booking.BOOKING_NO_SLOTS_TEXT),
    (0, 3, booking.BOOKING_NO_SLOTS_CLOSED_TEXT),
    (2, 0, booking.BOOKING_NO_SLOTS_BOOKED_TEXT),
    (2, 1, booking.BOOKING_NO_SLOTS_BOOKED_TEXT),  # смешано -> честнее "занято", не молчим про закрытое
])
async def test_no_free_slots_text_distinguishes_reason(booked, closed, expected_const):
    pool, conn = _mock_pool()
    conn.fetchrow = AsyncMock(return_value={"booked": booked, "closed": closed})

    with patch.object(booking, "get_pool", AsyncMock(return_value=pool)):
        text = await booking._no_free_slots_text()

    assert text == expected_const
    query = conn.fetchrow.await_args.args[0]
    assert "EXISTS" in query and "bookings" in query and "booking_slots" in query


@pytest.mark.asyncio
async def test_cb_book_service_uses_distinguishing_text_when_no_free_slots():
    cb = _make_callback(data="book_svc:consultation")
    state = _make_state({})

    with patch.object(booking, "_get_free_slots", AsyncMock(return_value=[])), \
         patch.object(booking, "_no_free_slots_text", AsyncMock(return_value="ЗАКРЫТО-ТЕКСТ")):
        await booking.cb_book_service(cb, state)

    cb.message.edit_text.assert_awaited_once()
    assert cb.message.edit_text.await_args.args[0] == "ЗАКРЫТО-ТЕКСТ"


@pytest.mark.asyncio
async def test_cb_book_day_back_uses_distinguishing_text_when_no_free_slots():
    cb = _make_callback(data="book_day_back")

    with patch.object(booking, "_get_free_slots", AsyncMock(return_value=[])), \
         patch.object(booking, "_no_free_slots_text", AsyncMock(return_value="ЗАНЯТО-ТЕКСТ")):
        await booking.cb_book_day_back(cb)

    cb.message.edit_text.assert_awaited_once()
    assert cb.message.edit_text.await_args.args[0] == "ЗАНЯТО-ТЕКСТ"


# ── (б) reply-клавиатура снимается во всех ветках отмены process_contact ───

@pytest.mark.asyncio
async def test_process_contact_missing_fields_removes_reply_keyboard():
    """Анкета потеряна (TTL/гонка) — раньше показывал только инлайн-клавиатуру
    _booking_restart_keyboard(), reply-клавиатура "Поделиться номером" оставалась."""
    state = _make_state({})  # все обязательные поля отсутствуют
    message = _make_message(text="+7 900 123-45-67")
    bot = AsyncMock()
    pool, conn = _mock_pool()

    with patch.object(booking, "get_pool", AsyncMock(return_value=pool)):
        await booking.process_contact(message, state, bot)

    state.clear.assert_awaited_once()
    assert message.answer.await_count == 2
    second_call = message.answer.await_args_list[1]
    assert isinstance(second_call.kwargs.get("reply_markup"), ReplyKeyboardRemove)


@pytest.mark.asyncio
async def test_process_contact_slot_taken_by_someone_else_removes_reply_keyboard():
    """Слот заняли, пока клиент вводил номер (claimed_id=None) — та же находка."""
    state = _make_state(FULL_DATA)
    message = _make_message(text="+7 900 123-45-67")
    bot = AsyncMock()
    pool, conn = _mock_pool()
    conn.fetchval = AsyncMock(return_value=None)  # захват слота не удался

    with patch.object(booking, "get_pool", AsyncMock(return_value=pool)):
        await booking.process_contact(message, state, bot)

    state.clear.assert_awaited_once()
    assert message.answer.await_count == 2
    second_call = message.answer.await_args_list[1]
    assert isinstance(second_call.kwargs.get("reply_markup"), ReplyKeyboardRemove)


@pytest.mark.asyncio
async def test_process_contact_success_path_still_removes_reply_keyboard_once():
    """Контроль: успешный путь (не затронут этим треком) всё ещё снимает
    клавиатуру ровно один раз через 'Номер получен ✅' (не должно задвоиться)."""
    state = _make_state(FULL_DATA)
    message = _make_message(text="+7 900 123-45-67")
    bot = AsyncMock()
    pool, conn = _mock_pool()
    conn.fetchval = AsyncMock(return_value=42)

    with patch.object(booking, "get_pool", AsyncMock(return_value=pool)), \
         patch.object(booking, "build_google_calendar_url", return_value="https://x"), \
         patch.object(booking, "generate_ics", return_value=b"X"), \
         patch("services.scheduler.schedule_booking_reminders", AsyncMock()):
        await booking.process_contact(message, state, bot)

    remove_calls = [
        c for c in message.answer.await_args_list
        if isinstance(c.kwargs.get("reply_markup"), ReplyKeyboardRemove)
    ]
    assert len(remove_calls) == 1
