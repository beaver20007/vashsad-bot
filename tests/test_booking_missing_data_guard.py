"""process_contact (handlers/booking.py, BookingForm.waiting_contact) не должен падать
с KeyError, когда анкета записи неполная (например, data пережила TTL дольше state —
см. docs/ORCHESTRATOR.md, fix/fsm-data-ttl-margin). Клиент получает понятное сообщение
без слова «ошибка», в лог уходят только ИМЕНА недостающих полей, без значений.
"""
import logging
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

# Контрольные значения, которые НЕ должны попасть в лог ни при каких обстоятельствах.
CLIENT_NAME = "Марина Петрова"
CLIENT_PHONE = "+7 900 123-45-67"


def _make_message(text: str | None, user_id: int = 1288492012) -> MagicMock:
    msg = MagicMock()
    msg.text = text
    msg.from_user = SimpleNamespace(id=user_id, first_name=CLIENT_NAME, username="marina")
    msg.answer = AsyncMock()
    msg.answer_document = AsyncMock()
    return msg


def _mock_pool():
    pool = MagicMock()
    conn = AsyncMock()
    pool.acquire = MagicMock(return_value=AsyncMock(
        __aenter__=AsyncMock(return_value=conn),
        __aexit__=AsyncMock(return_value=False),
    ))
    return pool, conn


def _make_state(data: dict) -> AsyncMock:
    state = AsyncMock()
    state.get_data = AsyncMock(return_value=dict(data))
    state.clear = AsyncMock()
    return state


# ── Отсутствующие/пустые поля не роняют хендлер ────────────────────────────

@pytest.mark.asyncio
@pytest.mark.parametrize("missing_field", ["slot_id", "slot_dt", "service_key", "service_price"])
async def test_single_missing_field_does_not_raise(missing_field):
    data = {k: v for k, v in FULL_DATA.items() if k != missing_field}
    state = _make_state(data)
    message = _make_message(CLIENT_PHONE)
    bot = AsyncMock()
    pool, conn = _mock_pool()

    with patch.object(booking, "get_pool", AsyncMock(return_value=pool)):
        await booking.process_contact(message, state, bot)  # не должно бросить исключение

    conn.execute.assert_not_called()  # заявка не создана из неполных данных
    state.clear.assert_awaited_once()
    message.answer.assert_awaited_once()
    sent_text = message.answer.await_args.args[0]
    assert "ошибка" not in sent_text.lower()
    assert "/book" in sent_text


@pytest.mark.asyncio
async def test_several_missing_fields_does_not_raise():
    data = {"slot_id": 7}  # slot_dt, service_key, service_price отсутствуют
    state = _make_state(data)
    message = _make_message(CLIENT_PHONE)
    bot = AsyncMock()
    pool, conn = _mock_pool()

    with patch.object(booking, "get_pool", AsyncMock(return_value=pool)):
        await booking.process_contact(message, state, bot)

    conn.execute.assert_not_called()
    message.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_empty_string_field_does_not_raise():
    data = {**FULL_DATA, "service_key": ""}
    state = _make_state(data)
    message = _make_message(CLIENT_PHONE)
    bot = AsyncMock()
    pool, conn = _mock_pool()

    with patch.object(booking, "get_pool", AsyncMock(return_value=pool)):
        await booking.process_contact(message, state, bot)

    conn.execute.assert_not_called()
    message.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_none_field_does_not_raise():
    data = {**FULL_DATA, "slot_dt": None}
    state = _make_state(data)
    message = _make_message(CLIENT_PHONE)
    bot = AsyncMock()
    pool, conn = _mock_pool()

    with patch.object(booking, "get_pool", AsyncMock(return_value=pool)):
        await booking.process_contact(message, state, bot)

    conn.execute.assert_not_called()
    message.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_missing_or_empty_phone_text_does_not_raise():
    """Если в состоянии waiting_contact пришёл не текст (message.text=None) или пустая строка."""
    state = _make_state(FULL_DATA)
    message = _make_message(None)  # например, стикер/фото вместо текста
    bot = AsyncMock()
    pool, conn = _mock_pool()

    with patch.object(booking, "get_pool", AsyncMock(return_value=pool)):
        await booking.process_contact(message, state, bot)

    conn.execute.assert_not_called()
    message.answer.assert_awaited_once()


# ── Сообщение клиенту: тон ВашСада, без технических слов ───────────────────

@pytest.mark.asyncio
async def test_client_message_is_on_brand_and_actionable():
    state = _make_state({})  # все поля отсутствуют
    message = _make_message(CLIENT_PHONE)
    bot = AsyncMock()
    pool, conn = _mock_pool()

    with patch.object(booking, "get_pool", AsyncMock(return_value=pool)):
        await booking.process_contact(message, state, bot)

    sent_text = message.answer.await_args.args[0]
    for banned in ("ошибка", "error", "exception", "keyerror", "traceback", "null", "none"):
        assert banned not in sent_text.lower(), f"технический/запрещённый термин {banned!r} в тексте клиенту"
    assert "/book" in sent_text  # понятное действие — что делать дальше


# ── Лог: только имена полей, без значений (имя, телефон, адрес) ────────────

@pytest.mark.asyncio
async def test_log_contains_field_names_but_not_client_data(caplog):
    data = {"slot_id": 7, "service_key": "consultation"}  # нет slot_dt, service_price
    state = _make_state(data)
    message = _make_message(CLIENT_PHONE)
    bot = AsyncMock()
    pool, conn = _mock_pool()

    with caplog.at_level(logging.ERROR, logger="handlers.booking"), \
         patch.object(booking, "get_pool", AsyncMock(return_value=pool)):
        await booking.process_contact(message, state, bot)

    log_text = " ".join(r.getMessage() for r in caplog.records)
    assert "slot_dt" in log_text
    assert "service_price" in log_text
    assert CLIENT_NAME not in log_text
    assert CLIENT_PHONE not in log_text
    assert "900" not in log_text  # часть телефона тоже не должна просочиться


@pytest.mark.asyncio
async def test_log_for_missing_phone_names_phone_field_not_value(caplog):
    state = _make_state(FULL_DATA)
    message = _make_message("")
    bot = AsyncMock()
    pool, conn = _mock_pool()

    with caplog.at_level(logging.ERROR, logger="handlers.booking"), \
         patch.object(booking, "get_pool", AsyncMock(return_value=pool)):
        await booking.process_contact(message, state, bot)

    log_text = " ".join(r.getMessage() for r in caplog.records)
    assert "phone" in log_text
    assert CLIENT_PHONE not in log_text


# ── Регресс: полная заявка обрабатывается как раньше ───────────────────────

@pytest.mark.asyncio
async def test_full_data_still_creates_booking_as_before():
    state = _make_state(FULL_DATA)
    message = _make_message(CLIENT_PHONE)
    bot = AsyncMock()
    pool, conn = _mock_pool()
    conn.fetchval = AsyncMock(return_value=99)

    with patch.object(booking, "get_pool", AsyncMock(return_value=pool)), \
         patch.object(booking, "build_google_calendar_url", return_value="https://calendar.google.com/x"), \
         patch.object(booking, "generate_ics", return_value=b"BEGIN:VCALENDAR"), \
         patch("services.scheduler.schedule_booking_reminders", AsyncMock()):
        await booking.process_contact(message, state, bot)

    assert conn.execute.await_count >= 2  # INSERT INTO bookings + UPDATE booking_slots
    insert_call = conn.execute.await_args_list[0]
    assert "INSERT INTO bookings" in insert_call.args[0]
    assert insert_call.args[1:] == (
        message.from_user.id, 7, "consultation", "Онлайн-консультация 60 мин", 2500, CLIENT_PHONE,
    )

    message.answer.assert_awaited_once()
    confirm_text = message.answer.await_args.args[0]
    assert "Запись подтверждена" in confirm_text
    state.clear.assert_awaited_once()
