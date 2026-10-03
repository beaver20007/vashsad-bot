"""Доработка PR #53 по ревью 2026-10-03: свободная заявка текстом, корректность
напоминаний (не шлём отменённой/перенесённой записи, снимаем джобы при
отмене/переносе, восстанавливаем при старте бота), атомарный захват слота
(двойное бронирование) и защита от подмены цены в callback_data.
"""
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from handlers import booking
from services import scheduler as scheduler_module


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


def _make_message(
    text: str | None = None, contact=None, user_id: int = 777,
    username: str | None = "client_u", first_name: str = "Клиент",
):
    msg = MagicMock()
    msg.text = text
    msg.contact = contact
    msg.from_user = SimpleNamespace(id=user_id, first_name=first_name, username=username)
    msg.answer = AsyncMock()
    return msg


def _make_state(data: dict | None = None) -> AsyncMock:
    state = AsyncMock()
    state.get_data = AsyncMock(return_value=dict(data or {}))
    state.update_data = AsyncMock()
    state.set_state = AsyncMock()
    state.clear = AsyncMock()
    return state


# ── Свободная заявка (BookingRequest.waiting_text) ─────────────────────────

@pytest.mark.asyncio
async def test_leave_request_free_text_notifies_staff_and_confirms_client():
    state = _make_state({"service_key": "consultation"})
    message = _make_message(text="Хочу обсудить живую изгородь, удобно по вечерам")
    bot = AsyncMock()
    bot.send_message = AsyncMock(return_value=MagicMock())

    with patch.object(booking, "BOOKING_RECIPIENT_IDS", [111]), \
         patch.object(booking, "DESIGNER_TELEGRAM_ID", 0), \
         patch.object(booking, "DESIGNER_TELEGRAM_ID_2", 0):
        await booking.process_leave_request(message, state, bot)

    bot.send_message.assert_awaited_once()
    staff_text = bot.send_message.await_args.args[1]
    assert "живую изгородь" in staff_text
    assert "@client_u" in staff_text
    assert str(message.from_user.id) in staff_text  # полный id допустим в самом сообщении сотруднику

    kb = bot.send_message.await_args.kwargs["reply_markup"]
    urls = [b.url for row in kb.inline_keyboard for b in row]
    assert "https://t.me/client_u" in urls

    # Reply-keyboard убирается коротким сообщением, затем идёт подтверждение.
    assert message.answer.await_count == 2
    assert "✅" in message.answer.await_args.args[0] or "Заявка принята" in message.answer.await_args.args[0]
    state.clear.assert_awaited_once()


@pytest.mark.asyncio
async def test_leave_request_html_escapes_client_text():
    state = _make_state({})
    message = _make_message(text="<b>жирный</b> & тест")
    bot = AsyncMock()
    bot.send_message = AsyncMock(return_value=MagicMock())

    with patch.object(booking, "BOOKING_RECIPIENT_IDS", [111]):
        await booking.process_leave_request(message, state, bot)

    staff_text = bot.send_message.await_args.args[1]
    assert "<b>жирный</b>" not in staff_text
    assert "&lt;b&gt;" in staff_text


@pytest.mark.asyncio
async def test_leave_request_own_contact_used_as_phone():
    contact = SimpleNamespace(user_id=777, phone_number="+7 900 111-22-33")
    state = _make_state({})
    message = _make_message(text=None, contact=contact)
    bot = AsyncMock()
    bot.send_message = AsyncMock(return_value=MagicMock())

    with patch.object(booking, "BOOKING_RECIPIENT_IDS", [111]):
        await booking.process_leave_request(message, state, bot)

    staff_text = bot.send_message.await_args.args[1]
    assert "+7 900 111-22-33" in staff_text


@pytest.mark.asyncio
async def test_leave_request_no_username_uses_tg_user_link():
    state = _make_state({})
    message = _make_message(text="Заявка без username", username=None)
    bot = AsyncMock()
    bot.send_message = AsyncMock(return_value=MagicMock())

    with patch.object(booking, "BOOKING_RECIPIENT_IDS", [111]):
        await booking.process_leave_request(message, state, bot)

    staff_text = bot.send_message.await_args.args[1]
    assert "нет username" in staff_text
    kb = bot.send_message.await_args.kwargs["reply_markup"]
    urls = [b.url for row in kb.inline_keyboard for b in row]
    assert f"tg://user?id={message.from_user.id}" in urls


@pytest.mark.asyncio
async def test_leave_request_non_text_asks_again_without_resetting_state():
    """Не текст и не свой контакт (например, стикер/фото) — переспрашиваем,
    не трогая state (анкету не сбрасываем)."""
    state = _make_state({"service_key": "consultation"})
    message = _make_message(text=None, contact=None)
    bot = AsyncMock()

    await booking.process_leave_request(message, state, bot)

    message.answer.assert_awaited_once()
    state.clear.assert_not_called()
    bot.send_message.assert_not_called()


# ── Напоминания: не шлём отменённой/перенесённой записи ────────────────────

@pytest.mark.asyncio
async def test_reminder_not_sent_for_cancelled_booking():
    pool, conn = _mock_pool()
    scheduled_dt = datetime(2026, 10, 10, 10, 0)
    conn.fetchrow = AsyncMock(return_value={
        "telegram_id": 777, "status": "cancelled", "slot_dt": scheduled_dt,
    })
    bot = AsyncMock()

    with patch("services.database.get_pool", new_callable=AsyncMock, return_value=pool):
        await scheduler_module._send_booking_reminder(bot, 55, scheduled_dt, "24h")

    bot.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_reminder_not_sent_when_slot_dt_changed_by_reschedule():
    pool, conn = _mock_pool()
    scheduled_dt = datetime(2026, 10, 10, 10, 0)
    live_dt = datetime(2026, 10, 12, 15, 0)  # запись перенесена на другое время
    conn.fetchrow = AsyncMock(return_value={
        "telegram_id": 777, "status": "confirmed", "slot_dt": live_dt,
    })
    bot = AsyncMock()

    with patch("services.database.get_pool", new_callable=AsyncMock, return_value=pool):
        await scheduler_module._send_booking_reminder(bot, 55, scheduled_dt, "1h")

    bot.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_reminder_sent_when_still_confirmed_and_dt_matches():
    pool, conn = _mock_pool()
    scheduled_dt = datetime(2026, 10, 10, 10, 0)
    conn.fetchrow = AsyncMock(return_value={
        "telegram_id": 777, "status": "confirmed", "slot_dt": scheduled_dt,
    })
    bot = AsyncMock()

    with patch("services.database.get_pool", new_callable=AsyncMock, return_value=pool):
        await scheduler_module._send_booking_reminder(bot, 55, scheduled_dt, "24h")

    bot.send_message.assert_awaited_once()
    assert bot.send_message.await_args.args[0] == 777
    assert "24 часа" in bot.send_message.await_args.args[1]


@pytest.mark.asyncio
async def test_cancel_booking_reminders_removes_both_jobs():
    fake_scheduler = MagicMock()
    with patch.object(scheduler_module, "_scheduler_instance", fake_scheduler):
        scheduler_module.cancel_booking_reminders(55)

    fake_scheduler.remove_job.assert_any_call("booking_remind_24h_55")
    fake_scheduler.remove_job.assert_any_call("booking_remind_1h_55")


@pytest.mark.asyncio
async def test_cancel_booking_reminders_ignores_missing_job():
    from apscheduler.jobstores.base import JobLookupError
    fake_scheduler = MagicMock()
    fake_scheduler.remove_job.side_effect = JobLookupError("booking_remind_24h_55")
    with patch.object(scheduler_module, "_scheduler_instance", fake_scheduler):
        scheduler_module.cancel_booking_reminders(55)  # не должно бросить исключение


@pytest.mark.asyncio
async def test_booking_cancel_by_client_removes_reminder_jobs():
    pool, conn = _mock_pool()
    conn.fetchrow = AsyncMock(return_value={
        "telegram_id": 777, "slot_id": 9, "service_name": "Консультация",
    })
    callback = MagicMock()
    callback.data = "book_cancel:55"
    callback.from_user = SimpleNamespace(id=777)
    callback.message = MagicMock()
    callback.message.edit_text = AsyncMock()
    callback.answer = AsyncMock()
    bot = AsyncMock()

    with patch.object(booking, "get_pool", AsyncMock(return_value=pool)), \
         patch("services.scheduler.cancel_booking_reminders") as cancel_mock:
        await booking.cb_book_cancel(callback, bot)

    cancel_mock.assert_called_once_with(55)


@pytest.mark.asyncio
async def test_reschedule_all_booking_reminders_reschedules_future_confirmed():
    pool, conn = _mock_pool()
    rows = [
        {"id": 1, "slot_dt": datetime(2026, 11, 1, 10, 0)},
        {"id": 2, "slot_dt": datetime(2026, 11, 2, 11, 0)},
    ]
    conn.fetch = AsyncMock(return_value=rows)
    bot = AsyncMock()

    with patch("services.database.get_pool", new_callable=AsyncMock, return_value=pool), \
         patch.object(scheduler_module, "schedule_booking_reminders", AsyncMock()) as sched_mock:
        await scheduler_module.reschedule_all_booking_reminders(bot)

    assert sched_mock.await_count == 2
    sched_mock.assert_any_await(bot, 1, rows[0]["slot_dt"])
    sched_mock.assert_any_await(bot, 2, rows[1]["slot_dt"])


# ── Атомарный захват слота: двойное бронирование ────────────────────────────

@pytest.mark.asyncio
async def test_double_booking_same_slot_second_attempt_rejected():
    """Первый fetchval (захват UPDATE...RETURNING id) отдаёт id первому, второй
    вызов (слот уже занят) возвращает None — второй клиент получает отказ."""
    state = _make_state({
        "slot_id": 7,
        "slot_dt": datetime(2026, 10, 10, 10, 0).isoformat(),
        "service_key": "consultation",
        "service_price": 2500,
    })
    message = _make_message(text="+7 900 000-00-00")
    bot = AsyncMock()

    pool, conn = _mock_pool()
    conn.fetchval = AsyncMock(return_value=None)  # слот уже занят первым клиентом

    with patch.object(booking, "get_pool", AsyncMock(return_value=pool)):
        await booking.process_contact(message, state, bot)

    conn.fetchval.assert_awaited_once()  # только попытка захвата, INSERT не дошёл
    sent_text = message.answer.await_args.args[0]
    assert "уже заняли" in sent_text.lower()
    state.clear.assert_awaited_once()


# ── Защита от подмены цены в callback_data ──────────────────────────────────

@pytest.mark.asyncio
async def test_tampered_service_key_in_callback_is_rejected():
    callback = MagicMock()
    callback.data = "book_svc:gold_vip_free"  # несуществующий/подделанный ключ формата
    callback.answer = AsyncMock()
    callback.message = MagicMock()
    callback.message.edit_text = AsyncMock()
    state = _make_state({})

    await booking.cb_book_service(callback, state)

    callback.answer.assert_awaited_once()
    assert "недоступен" in callback.answer.await_args.args[0].lower()
    state.clear.assert_awaited_once()
    state.update_data.assert_not_called()
    callback.message.edit_text.assert_not_called()


# ── html.escape для first_name в уведомлениях принимающим (ревью 03.10) ────

HOSTILE_NAME = "<b>Анна & Ко</b>"


@pytest.mark.asyncio
async def test_booking_confirmation_notification_escapes_client_name():
    """Имя клиента с HTML-разметкой не должно пролезть в сообщение сотруднику
    как настоящая разметка — иначе Telegram вернёт ошибку парсинга или сломает
    верстку остального сообщения."""
    state = _make_state({
        "slot_id": 7,
        "slot_dt": datetime(2026, 10, 10, 10, 0).isoformat(),
        "service_key": "consultation",
        "service_price": 2500,
    })
    message = _make_message(text="+7 900 000-00-00", first_name=HOSTILE_NAME)
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

    staff_text = bot.send_message.await_args.args[1]
    assert "<b>Анна & Ко</b>" not in staff_text
    assert "&lt;b&gt;Анна &amp; Ко&lt;/b&gt;" in staff_text


@pytest.mark.asyncio
async def test_leave_request_notification_escapes_client_name():
    state = _make_state({})
    message = _make_message(text="Хочу консультацию", first_name=HOSTILE_NAME)
    bot = AsyncMock()
    bot.send_message = AsyncMock(return_value=MagicMock())

    with patch.object(booking, "BOOKING_RECIPIENT_IDS", [111]):
        await booking.process_leave_request(message, state, bot)

    staff_text = bot.send_message.await_args.args[1]
    assert "<b>Анна & Ко</b>" not in staff_text
    assert "&lt;b&gt;Анна &amp; Ко&lt;/b&gt;" in staff_text
