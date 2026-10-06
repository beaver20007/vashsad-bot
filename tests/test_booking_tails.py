"""Хвосты BookingForm (автономная очередь, трек 3, 2026-10-03), часть (а):
закрытый сотрудником слот неотличим от занятого клиентом в списке «Слоты» —
различаем без новой миграции (EXISTS по bookings.status, не новая колонка).
"""
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from handlers import booking


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


def _make_callback(data: str = "", user_id: int = 100000555) -> MagicMock:
    cb = MagicMock()
    cb.data = data
    cb.from_user = SimpleNamespace(id=user_id, first_name="Сотрудник", username="staff_u")
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.message.answer = AsyncMock()
    cb.answer = AsyncMock()
    return cb


def test_slot_status_icon_differentiates_closed_from_booked_and_free():
    assert booking._slot_status_icon(is_booked=False, has_client_booking=False) == "🟢"
    assert booking._slot_status_icon(is_booked=True, has_client_booking=True) == "🔴"
    assert booking._slot_status_icon(is_booked=True, has_client_booking=False) == "🔒"


@pytest.mark.asyncio
async def test_staff_slots_list_shows_three_distinct_states_without_schema_migration():
    pool, conn = _mock_pool()
    conn.fetch = AsyncMock(return_value=[
        {"slot_dt": datetime(2026, 11, 1, 10, 0), "is_booked": False, "has_client_booking": False},
        {"slot_dt": datetime(2026, 11, 1, 11, 0), "is_booked": True, "has_client_booking": True},
        {"slot_dt": datetime(2026, 11, 1, 12, 0), "is_booked": True, "has_client_booking": False},
    ])
    cb = _make_callback()

    with patch.object(booking, "get_pool", AsyncMock(return_value=pool)), \
         patch.object(booking, "_is_booking_staff", return_value=True):
        await booking.cb_list_slots(cb)

    # Запрос различает "занят клиентом" от "закрыт вручную" через EXISTS по
    # bookings.status — НЕ через новую колонку в booking_slots.
    query = conn.fetch.await_args.args[0]
    assert "EXISTS" in query and "bookings" in query and "booking_slots" in query

    text = cb.message.answer.await_args.args[0]
    slot_lines = [ln for ln in text.splitlines() if "МСК" in ln]
    icons = [ln[0] for ln in slot_lines]
    assert icons == ["🟢", "🔴", "🔒"], text
    assert "закрыт вручную" in text  # легенда для сотрудника


# ── (б) один слот не достаётся двум принимающим одновременно ───────────────
# Код уже атомарен (conditional UPDATE...RETURNING, не "проверить и
# записать") — тестов на это в репозитории не было, закрываем хвост.

@pytest.mark.asyncio
async def test_two_staff_closing_same_slot_only_first_succeeds():
    """Атомарный conditional UPDATE...RETURNING: второй вызов видит слот уже
    занятым сразу, а не по итогам отдельной проверки до записи."""
    pool, conn = _mock_pool()
    conn.fetchval = AsyncMock(side_effect=[42, None])  # 1-й захватывает, 2-й - уже занято

    cb_a = _make_callback(data="badm_close:42", user_id=111111)  # сотрудник А
    cb_b = _make_callback(data="badm_close:42", user_id=222222)  # сотрудник Б, тот же слот

    with patch.object(booking, "get_pool", AsyncMock(return_value=pool)), \
         patch.object(booking, "_is_booking_staff", return_value=True):
        await booking.cb_badm_close(cb_a)
        await booking.cb_badm_close(cb_b)

    assert conn.fetchval.await_count == 2
    cb_a.answer.assert_awaited_once_with("Слот закрыт", show_alert=True)
    cb_b.answer.assert_awaited_once_with("Слот уже занят/закрыт", show_alert=True)


@pytest.mark.asyncio
async def test_two_staff_rescheduling_different_bookings_to_same_new_slot_only_first_succeeds():
    """Два сотрудника переносят ДВЕ РАЗНЫЕ записи на ОДИН И ТОТ ЖЕ новый слот —
    второй должен получить отказ, а не создать вторую запись на занятый слот."""
    pool, conn = _mock_pool()
    old_row = {
        "telegram_id": 50001, "slot_id": 10, "service_key": "consultation",
        "service_name": "Консультация", "service_price": 2500, "phone": "+70000000001",
    }
    conn.fetchrow = AsyncMock(return_value=old_row)
    new_dt = datetime(2026, 11, 2, 10, 0)
    # Порядок fetchval в УСПЕШНОМ прогоне: захват нового слота, SELECT slot_dt,
    # INSERT...RETURNING id новой записи. Во ВТОРОМ (неуспешном) — только захват.
    conn.fetchval = AsyncMock(side_effect=[77, new_dt, 999, None])

    bot = AsyncMock()
    cb_a = _make_callback(data="badm_resched_pick:901:55", user_id=111111)
    cb_b = _make_callback(data="badm_resched_pick:902:55", user_id=222222)  # тот же new_slot_id=55

    with patch.object(booking, "get_pool", AsyncMock(return_value=pool)), \
         patch.object(booking, "_is_booking_staff", return_value=True), \
         patch("services.scheduler.cancel_booking_reminders"), \
         patch("services.scheduler.schedule_booking_reminders", AsyncMock()):
        await booking.cb_badm_resched_pick(cb_a, bot)
        await booking.cb_badm_resched_pick(cb_b, bot)

    cb_a.answer.assert_awaited_once()
    assert "Перенесено" in cb_a.answer.await_args.args[0]
    cb_b.answer.assert_awaited_once_with("Этот слот уже занят, выберите другой", show_alert=True)


# ── (в) после "Отмена" в заявке — правильная reply-клавиатура ──────────────

@pytest.mark.asyncio
async def test_leave_request_cancel_restores_main_reply_keyboard():
    """Одноразовая клавиатура "Поделиться номером" не прячется сама от тапа по
    инлайн-кнопке "Отмена" (one_time_keyboard реагирует только на использование
    СЕБЯ/любое сообщение) — после отмены должна явно вернуться обычная
    клавиатура главного меню."""
    from handlers.start import MAIN_KEYBOARD

    cb = _make_callback()
    state = AsyncMock()
    state.clear = AsyncMock()

    await booking.cb_book_leave_cancel(cb, state)

    state.clear.assert_awaited_once()
    cb.message.answer.assert_awaited_once()
    kwargs = cb.message.answer.await_args.kwargs
    assert kwargs.get("reply_markup") is MAIN_KEYBOARD
