"""Валидация и экранирование телефона в process_contact (ревью 03.10, трек Т1):
текстовый телефон принимается только в разумном виде (цифры/пробелы/скобки/
дефис/ведущий "+", 10-15 цифр после очистки, не длиннее bookings.phone
VARCHAR(32)); номер из message.contact не валидируется по формату (данные от
Telegram), только ограничивается длиной. Телефон всегда экранируется перед
подстановкой в HTML-сообщения.
"""
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

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


def _make_message(text: str | None = None, contact=None, user_id: int = 100000001) -> MagicMock:
    msg = MagicMock()
    msg.text = text
    msg.contact = contact
    msg.from_user = SimpleNamespace(id=user_id, first_name="Клиент", username="client_u")
    msg.answer = AsyncMock()
    msg.answer_document = AsyncMock()
    return msg


def _make_state(data: dict) -> AsyncMock:
    state = AsyncMock()
    state.get_data = AsyncMock(return_value=dict(data))
    state.clear = AsyncMock()
    state.update_data = AsyncMock()
    state.set_state = AsyncMock()
    return state


# ── _normalize_text_phone — юнит-проверки формата ──────────────────────────

@pytest.mark.parametrize("raw", [
    "+7 (999) 123-45-67",
    "89991234567",
    "+7 999 123 45 67",
    "7-999-123-45-67",
])
def test_normalize_text_phone_accepts_reasonable_formats(raw):
    assert booking._normalize_text_phone(raw) is not None


@pytest.mark.parametrize("raw", [
    "позвоните мне",
    "+7 999 <b>123</b>-45-67",
    "99",  # меньше 10 цифр
    "1" * 40,  # длиннее 32 символов
    "",
    "   ",
])
def test_normalize_text_phone_rejects_bad_input(raw):
    assert booking._normalize_text_phone(raw) is None


# ── process_contact: текст с буквами/разметкой отклоняется ─────────────────

@pytest.mark.asyncio
async def test_text_with_html_tag_rejected_state_preserved_no_insert():
    state = _make_state(FULL_DATA)
    message = _make_message(text="мой номер <b>+7 900 123-45-67</b>")
    bot = AsyncMock()
    pool, conn = _mock_pool()

    with patch.object(booking, "get_pool", AsyncMock(return_value=pool)):
        await booking.process_contact(message, state, bot)

    conn.fetchval.assert_not_called()  # до захвата слота не дошло
    state.clear.assert_not_called()  # state НЕ сброшен — анкета цела, ждём номер ещё раз
    message.answer.assert_awaited_once()
    sent_text = message.answer.await_args.args[0]
    assert "не похож" in sent_text.lower()


@pytest.mark.asyncio
async def test_too_long_text_rejected():
    state = _make_state(FULL_DATA)
    message = _make_message(text="7" * 40)  # длиннее 32 символов
    bot = AsyncMock()
    pool, conn = _mock_pool()

    with patch.object(booking, "get_pool", AsyncMock(return_value=pool)):
        await booking.process_contact(message, state, bot)

    conn.fetchval.assert_not_called()
    state.clear.assert_not_called()
    sent_text = message.answer.await_args.args[0]
    assert "не похож" in sent_text.lower()


# ── Разумные форматы принимаются ────────────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.parametrize("raw_phone", ["+7 (999) 123-45-67", "89991234567"])
async def test_reasonable_text_phone_accepted(raw_phone):
    state = _make_state(FULL_DATA)
    message = _make_message(text=raw_phone)
    bot = AsyncMock()
    pool, conn = _mock_pool()
    conn.fetchval = AsyncMock(return_value=42)

    with patch.object(booking, "get_pool", AsyncMock(return_value=pool)), \
         patch.object(booking, "build_google_calendar_url", return_value="https://x"), \
         patch.object(booking, "generate_ics", return_value=b"X"), \
         patch("services.scheduler.schedule_booking_reminders", AsyncMock()):
        await booking.process_contact(message, state, bot)

    assert conn.fetchval.await_count == 2  # захват слота + INSERT
    insert_call = conn.fetchval.await_args_list[1]
    assert insert_call.args[-1] == raw_phone  # телефон сохраняется как прислан, без искажений
    state.clear.assert_awaited_once()


@pytest.mark.asyncio
async def test_contact_button_phone_accepted_without_format_check():
    """Номер от кнопки "Поделиться номером" не проверяется по формату (это
    данные от Telegram, не свободный ввод) — только ограничение длины."""
    contact = SimpleNamespace(user_id=100000001, phone_number="+79991234567")
    state = _make_state(FULL_DATA)
    message = _make_message(text=None, contact=contact)
    bot = AsyncMock()
    pool, conn = _mock_pool()
    conn.fetchval = AsyncMock(return_value=42)

    with patch.object(booking, "get_pool", AsyncMock(return_value=pool)), \
         patch.object(booking, "build_google_calendar_url", return_value="https://x"), \
         patch.object(booking, "generate_ics", return_value=b"X"), \
         patch("services.scheduler.schedule_booking_reminders", AsyncMock()):
        await booking.process_contact(message, state, bot)

    insert_call = conn.fetchval.await_args_list[1]
    assert insert_call.args[-1] == "+79991234567"
    state.clear.assert_awaited_once()


# ── Экранирование телефона в HTML-сообщениях ────────────────────────────────

HOSTILE_PHONE = "+7<b>999</b>1234567"  # не пройдёт валидацию формата как текст,
# поэтому проверяем через contact (который формат не проверяет) — именно так
# потенциально опасное значение телефона может попасть в сообщение.


@pytest.mark.asyncio
async def test_hostile_contact_phone_is_escaped_in_all_html_messages():
    contact = SimpleNamespace(user_id=100000001, phone_number=HOSTILE_PHONE)
    state = _make_state(FULL_DATA)
    message = _make_message(text=None, contact=contact)
    bot = AsyncMock()
    bot.send_message = AsyncMock(return_value=MagicMock())
    pool, conn = _mock_pool()
    conn.fetchval = AsyncMock(return_value=42)

    with patch.object(booking, "get_pool", AsyncMock(return_value=pool)), \
         patch.object(booking, "build_google_calendar_url", return_value="https://x"), \
         patch.object(booking, "generate_ics", return_value=b"X"), \
         patch.object(booking, "BOOKING_RECIPIENT_IDS", [111]), \
         patch("services.scheduler.schedule_booking_reminders", AsyncMock()):
        await booking.process_contact(message, state, bot)

    confirm_text = message.answer.await_args_list[-1].args[0]
    staff_text = bot.send_message.await_args.args[1]
    assert "<b>999</b>" not in confirm_text
    assert "<b>999</b>" not in staff_text
    assert "&lt;b&gt;999&lt;/b&gt;" in confirm_text
    assert "&lt;b&gt;999&lt;/b&gt;" in staff_text


@pytest.mark.asyncio
async def test_leave_request_hostile_contact_phone_is_escaped():
    contact = SimpleNamespace(user_id=100000001, phone_number=HOSTILE_PHONE)
    state = _make_state({})
    message = _make_message(text=None, contact=contact)
    bot = AsyncMock()
    bot.send_message = AsyncMock(return_value=MagicMock())

    with patch.object(booking, "BOOKING_RECIPIENT_IDS", [111]):
        await booking.process_leave_request(message, state, bot)

    staff_text = bot.send_message.await_args.args[1]
    assert "<b>999</b>" not in staff_text
    assert "&lt;b&gt;999&lt;/b&gt;" in staff_text
