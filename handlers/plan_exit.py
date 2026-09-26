"""Выход из анкеты «План участка»: любая команда и любая кнопка, не являющаяся шагом анкеты, её завершают.

Почему outer-middleware. Обработчики шагов PlanForm.waiting_area/style/wishes принимают любое сообщение,
а роутер плана стоит в bot.py раньше остальных: без сброса состояния команда вроде /price уходила в анкету
как «ответ» (а кнопки старых меню срабатывали, но оставляли пользователя в анкете). Inner-middleware и
фильтры на хендлерах не подходят: состояние уже прочитано и обработчик выбран. Outer-middleware на
message/callback_query выполняется до фильтров, поэтому может сбросить состояние и обновить raw_state,
который aiogram кладёт в data на предыдущем шаге (fsm/middleware.py).

Действует только когда пользователь в состоянии PlanForm; остальные FSM-анкеты не затрагиваются.
"""
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from handlers.plan import PlanForm

log = logging.getLogger(__name__)

PLAN_STATES = {s.state for s in PlanForm.__all_states__}
# команды, которые сами являются входом в анкету (_start_plan сам всё сбрасывает)
PLAN_COMMANDS = {"plan"}
# callback-данные шагов анкеты (budget:*, plan:confirm/restart) и оценка NPS: она не уводит пользователя из анкеты
PLAN_CALLBACK_PREFIXES = ("budget:", "plan:", "nps:")


def _command_name(text: str) -> str:
    return text[1:].split(maxsplit=1)[0].split("@", 1)[0].lower() if len(text) > 1 else ""


def leaves_plan(event: TelegramObject) -> bool:
    """True, если событие уводит пользователя из анкеты плана участка."""
    if isinstance(event, Message):
        text = event.text or ""
        return text.startswith("/") and _command_name(text) not in PLAN_COMMANDS
    if isinstance(event, CallbackQuery):
        return not (event.data or "").startswith(PLAN_CALLBACK_PREFIXES)
    return False


class PlanExitMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        state = data.get("state")
        if state is not None and data.get("raw_state") in PLAN_STATES and leaves_plan(event):
            log.info("PlanForm: выход из анкеты (%s), состояние сброшено", data["raw_state"])
            await state.clear()
            data["raw_state"] = None
        return await handler(event, data)
