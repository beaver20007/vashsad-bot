"""Отмена и /start выходят из незавершённой FSM-анкеты (план участка), а не оставляют пользователя в ней."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from handlers import plan, start


def _ctx(storage: MemoryStorage, user_id: int = 1288492012) -> FSMContext:
    return FSMContext(storage=storage, key=StorageKey(bot_id=1, chat_id=user_id, user_id=user_id))


async def _stuck_in_plan(state: FSMContext, step: str) -> None:
    await state.set_state(getattr(plan.PlanForm, step))
    await state.update_data(area="6")


@pytest.mark.asyncio
@pytest.mark.parametrize("step", ["waiting_area", "waiting_style", "waiting_budget"])
async def test_cancel_button_clears_plan_state(step):
    state = _ctx(MemoryStorage())
    await _stuck_in_plan(state, step)

    callback = MagicMock()
    callback.from_user = SimpleNamespace(id=1288492012)
    callback.message.edit_text = AsyncMock()
    callback.answer = AsyncMock()

    await start.cb_cancel(callback, state)

    assert await state.get_state() is None
    assert await state.get_data() == {}


@pytest.mark.asyncio
@pytest.mark.parametrize("consent", [False, True])
async def test_start_command_clears_plan_state(consent):
    state = _ctx(MemoryStorage())
    await _stuck_in_plan(state, "waiting_style")

    message = MagicMock()
    message.text = "/start"
    message.from_user = SimpleNamespace(id=1288492012, username="u", first_name="P", language_code="ru")
    message.answer = AsyncMock()
    user = SimpleNamespace(pdn_consent_at=object() if consent else None)

    with patch("handlers.start.get_or_create_user", new_callable=AsyncMock, return_value=user), \
         patch("handlers.start._send_welcome", new_callable=AsyncMock), \
         patch("handlers.start.insert_analytics_event", new_callable=AsyncMock):
        await start.cmd_start(message, state)

    assert await state.get_state() is None


@pytest.mark.asyncio
async def test_plan_area_handler_no_longer_matches_after_cancel():
    """Регрессия: FSM-обработчик анкеты матчится только в её состоянии; после отмены состояния нет."""
    state = _ctx(MemoryStorage())
    await _stuck_in_plan(state, "waiting_area")
    assert await state.get_state() == plan.PlanForm.waiting_area.state  # без фикса так и остаётся после Отмены

    callback = MagicMock()
    callback.from_user = SimpleNamespace(id=1288492012)
    callback.message.edit_text = AsyncMock()
    callback.answer = AsyncMock()
    await start.cb_cancel(callback, state)

    assert await state.get_state() != plan.PlanForm.waiting_area.state
