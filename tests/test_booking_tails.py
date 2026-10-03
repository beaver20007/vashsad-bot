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
