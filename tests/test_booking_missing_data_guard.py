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
from aiogram.types import ReplyKeyboardRemove

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


def _make_message(text: str | None, user_id: int = 100000001) -> MagicMock:
    msg = MagicMock()
    msg.text = text
    msg.from_user = SimpleNamespace(id=user_id, first_name=CLIENT_NAME, username="marina")
    msg.answer = AsyncMock()
    msg.answer_document = AsyncMock()
    return msg


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


def _make_state(data: dict) -> AsyncMock:
    state = AsyncMock()
    state.get_data = AsyncMock(return_value=dict(data))
    state.clear = AsyncMock()
    state.set_data = AsyncMock()
    state.update_data = AsyncMock()
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
    # B2 (ночной бриф 05→06.10): второе сообщение снимает reply-клавиатуру
    # "Поделиться номером", которая иначе оставалась бы висеть после сброса анкеты.
    assert message.answer.await_count == 2
    sent_text = message.answer.await_args_list[0].args[0]
    kb = message.answer.await_args_list[0].kwargs["reply_markup"]
    buttons = [b.text for row in kb.inline_keyboard for b in row]
    assert "ошибка" not in sent_text.lower()
    assert any("Начать запись заново" in t for t in buttons)  # кнопка вместо "наберите /book"
    assert isinstance(message.answer.await_args_list[1].kwargs.get("reply_markup"), ReplyKeyboardRemove)


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
    assert message.answer.await_count == 2  # retry-текст + снятие reply-клавиатуры


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
    assert message.answer.await_count == 2  # retry-текст + снятие reply-клавиатуры


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
    assert message.answer.await_count == 2  # retry-текст + снятие reply-клавиатуры


@pytest.mark.asyncio
@pytest.mark.parametrize("text", [None, "", "   "])
async def test_missing_or_empty_phone_text_does_not_raise(text):
    """Анкета (слот/услуга) цела, но вместо номера пришёл не текст (None — например,
    стикер/фото), пустая строка или только пробелы: клиент остаётся в форме, данные
    анкеты и state не трогаем — это другой случай, чем реально утерянная анкета."""
    state = _make_state(FULL_DATA)
    message = _make_message(text)
    bot = AsyncMock()
    pool, conn = _mock_pool()

    with patch.object(booking, "get_pool", AsyncMock(return_value=pool)):
        await booking.process_contact(message, state, bot)  # не должно бросить исключение

    conn.execute.assert_not_called()
    state.clear.assert_not_called()  # форма НЕ сбрасывается — клиент остаётся в ней
    state.set_data.assert_not_called()
    state.update_data.assert_not_called()
    message.answer.assert_awaited_once()
    sent_text = message.answer.await_args.args[0]
    assert "номер телефона" in sent_text.lower()
    state.get_data.assert_awaited_once()  # анкету прочитали (проверили, что она цела)


@pytest.mark.asyncio
async def test_missing_form_field_takes_priority_over_missing_phone():
    """Если не хватает и поля анкеты, и телефона — срабатывает ветка потери анкеты
    (BOOKING_RETRY_TEXT + state.clear), а не просьба прислать телефон текстом."""
    data = {k: v for k, v in FULL_DATA.items() if k != "slot_id"}  # анкета неполная
    state = _make_state(data)
    message = _make_message(None)  # и телефон тоже не пришёл текстом
    bot = AsyncMock()
    pool, conn = _mock_pool()

    with patch.object(booking, "get_pool", AsyncMock(return_value=pool)):
        await booking.process_contact(message, state, bot)

    conn.execute.assert_not_called()
    state.clear.assert_awaited_once()
    assert message.answer.await_count == 2  # retry-текст + снятие reply-клавиатуры
    sent_text = message.answer.await_args_list[0].args[0]
    assert sent_text == booking.BOOKING_RETRY_TEXT
    assert "номер телефона" not in sent_text.lower()


# ── Сообщение клиенту: тон ВашСада, без технических слов ───────────────────

@pytest.mark.asyncio
async def test_client_message_is_on_brand_and_actionable():
    state = _make_state({})  # все поля отсутствуют
    message = _make_message(CLIENT_PHONE)
    bot = AsyncMock()
    pool, conn = _mock_pool()

    with patch.object(booking, "get_pool", AsyncMock(return_value=pool)):
        await booking.process_contact(message, state, bot)

    sent_text = message.answer.await_args_list[0].args[0]
    kb = message.answer.await_args_list[0].kwargs["reply_markup"]
    buttons = [b.text for row in kb.inline_keyboard for b in row]
    for banned in ("ошибка", "error", "exception", "keyerror", "traceback", "null", "none"):
        assert banned not in sent_text.lower(), f"технический/запрещённый термин {banned!r} в тексте клиенту"
    assert any("Начать запись заново" in t for t in buttons)  # понятное действие — кнопка, не команда


# ── Лог: только имена полей, без значений (имя, телефон, адрес) ────────────

@pytest.mark.asyncio
async def test_log_contains_field_names_but_not_client_data(caplog):
    data = {"slot_id": 7, "service_key": "consultation"}  # нет slot_dt, service_price
    state = _make_state(data)
    message = _make_message(CLIENT_PHONE)
    bot = AsyncMock()
    pool, conn = _mock_pool()

    with caplog.at_level(logging.WARNING, logger="handlers.booking"), \
         patch.object(booking, "get_pool", AsyncMock(return_value=pool)):
        await booking.process_contact(message, state, bot)

    log_text = " ".join(r.getMessage() for r in caplog.records)
    assert "slot_dt" in log_text
    assert "service_price" in log_text
    assert CLIENT_NAME not in log_text
    assert CLIENT_PHONE not in log_text
    assert "900" not in log_text  # часть телефона тоже не должна просочиться


@pytest.mark.asyncio
async def test_missing_form_field_logs_at_warning_not_error(caplog):
    """Потеря анкеты — ожидаемая ситуация (TTL/мини-апп), а не поломка кода: WARNING."""
    data = {"slot_id": 7}  # slot_dt, service_key, service_price отсутствуют
    state = _make_state(data)
    message = _make_message(CLIENT_PHONE)
    bot = AsyncMock()
    pool, conn = _mock_pool()

    with caplog.at_level(logging.WARNING, logger="handlers.booking"), \
         patch.object(booking, "get_pool", AsyncMock(return_value=pool)):
        await booking.process_contact(message, state, bot)

    levels = [r.levelname for r in caplog.records]
    assert levels == ["WARNING"]


@pytest.mark.asyncio
async def test_missing_phone_text_does_not_log_client_data(caplog):
    """Клиент прислал не текст вместо телефона — это не лог-достойное событие (ожидаемый
    пользовательский ввод), но даже если что-то залогируется, там не должно быть данных."""
    state = _make_state(FULL_DATA)
    message = _make_message("")
    bot = AsyncMock()
    pool, conn = _mock_pool()

    with caplog.at_level(logging.DEBUG, logger="handlers.booking"), \
         patch.object(booking, "get_pool", AsyncMock(return_value=pool)):
        await booking.process_contact(message, state, bot)

    assert caplog.records == []  # для этого случая ничего не логируется
    log_text = " ".join(r.getMessage() for r in caplog.records)
    assert CLIENT_PHONE not in log_text
    assert CLIENT_NAME not in log_text


# ── Регресс: полная заявка обрабатывается как раньше ───────────────────────

@pytest.mark.asyncio
async def test_full_data_still_creates_booking_as_before():
    """Регресс для track-booking-buttons (2026-10-03): INSERT теперь идёт через
    fetchval(... RETURNING id) вместо отдельного execute + второго SELECT за
    booking_id — поведение для клиента то же, внутренний вызов к БД другой."""
    state = _make_state(FULL_DATA)
    message = _make_message(CLIENT_PHONE)
    bot = AsyncMock()
    pool, conn = _mock_pool()
    # Слот захватывается атомарным UPDATE ... RETURNING id (conn.fetchval);
    # id=7 возвращается и на захват слота, и на INSERT ... RETURNING id.
    conn.fetchval = AsyncMock(return_value=7)

    with patch.object(booking, "get_pool", AsyncMock(return_value=pool)), \
         patch.object(booking, "build_google_calendar_url", return_value="https://calendar.google.com/x"), \
         patch.object(booking, "generate_ics", return_value=b"BEGIN:VCALENDAR"), \
         patch("services.scheduler.schedule_booking_reminders", AsyncMock()):
        await booking.process_contact(message, state, bot)

    assert conn.fetchval.await_count == 2  # захват слота + INSERT ... RETURNING id
    claim_call, insert_call = conn.fetchval.await_args_list
    assert "UPDATE booking_slots" in claim_call.args[0] and "is_booked=FALSE" in claim_call.args[0]
    assert "INSERT INTO bookings" in insert_call.args[0]
    assert insert_call.args[1:] == (
        message.from_user.id, 7, "consultation", "Онлайн-консультация 60 мин", 2500, CLIENT_PHONE,
    )

    conn.execute.assert_not_called()  # захват слота теперь через fetchval, не execute

    # Первое сообщение — "Номер получен" с ReplyKeyboardRemove, второе — подтверждение записи.
    assert message.answer.await_count == 2
    confirm_text = message.answer.await_args_list[1].args[0]
    assert "Запись подтверждена" in confirm_text
    state.clear.assert_awaited_once()
