"""Выходы из анкеты «План участка» (PlanForm): команды, кнопки меню, не-текст, повторный вход.

Тесты идут через настоящий Dispatcher (MemoryStorage) с роутером плана и «чужими» обработчиками после него,
в том же порядке, что в bot.py. Сеть Telegram подменена.
"""
from datetime import datetime
from pathlib import Path

import pytest
import pytest_asyncio
from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.session.base import BaseSession
from aiogram.filters import Command
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, Chat, Message, MessageEntity, PhotoSize, Update, User

from handlers import plan
from services import bot_texts

try:  # на старом коде модуля нет: тогда сценарии воспроизводят баг
    from handlers.plan_exit import PlanExitMiddleware
except ImportError:  # pragma: no cover
    PlanExitMiddleware = None

UID = 1288492012
ALL_STATES = ["waiting_area", "waiting_style", "waiting_budget", "waiting_wishes", "waiting_confirm"]


class FakeSession(BaseSession):
    def __init__(self):
        super().__init__()
        self.sent: list[tuple[str, dict]] = []

    async def close(self):  # pragma: no cover
        pass

    async def make_request(self, bot, method, timeout=None):
        self.sent.append((type(method).__name__, method.model_dump()))
        return True

    async def stream_content(self, *a, **k):  # pragma: no cover
        yield b""


@pytest_asyncio.fixture
async def env():
    calls: list[str] = []
    other = Router()  # «остальные» роутеры бота: стоят после plan.router, как в bot.py

    @other.message(Command("price"))
    async def _price(message: Message):
        calls.append("price")

    @other.callback_query(F.data == "menu:main")
    async def _menu_main(callback: CallbackQuery):
        calls.append("menu:main")

    @other.message(F.text)
    async def _chat(message: Message):
        calls.append("chat")

    dp = Dispatcher(storage=MemoryStorage())
    if PlanExitMiddleware is not None:  # так же, как в bot.py
        dp.message.outer_middleware(PlanExitMiddleware())
        dp.callback_query.outer_middleware(PlanExitMiddleware())
    dp.include_routers(plan.router, other)

    session = FakeSession()
    bot = Bot(token="123456:TEST", session=session)
    key = StorageKey(bot_id=bot.id, chat_id=UID, user_id=UID)
    yield SimpleEnv(dp, bot, key, calls, session)
    plan.router._parent_router = None
    other._parent_router = None


class SimpleEnv:
    def __init__(self, dp, bot, key, calls, session):
        self.dp, self.bot, self.key, self.calls, self.session = dp, bot, key, calls, session
        self._id = 0

    async def set_plan_state(self, step: str, **data):
        await self.dp.storage.set_state(self.key, getattr(plan.PlanForm, step))
        if data:
            await self.dp.storage.set_data(self.key, data)

    async def state(self):
        return await self.dp.storage.get_state(self.key)

    async def data(self):
        return await self.dp.storage.get_data(self.key)

    def _message(self, **kw) -> Message:
        self._id += 1
        return Message(message_id=self._id, date=datetime.now(), chat=Chat(id=UID, type="private"),
                       from_user=User(id=UID, is_bot=False, first_name="T"), **kw)

    async def text(self, text: str):
        ents = None
        if text.startswith("/"):
            ents = [MessageEntity(type="bot_command", offset=0, length=len(text.split()[0]))]
        msg = self._message(text=text, entities=ents)
        await self.dp.feed_update(self.bot, Update(update_id=self._id, message=msg))

    async def photo(self):
        msg = self._message(photo=[PhotoSize(file_id="f", file_unique_id="u", width=1, height=1)])
        await self.dp.feed_update(self.bot, Update(update_id=self._id, message=msg))

    async def button(self, data: str):
        self._id += 1
        cb = CallbackQuery(id=str(self._id), from_user=User(id=UID, is_bot=False, first_name="T"),
                           chat_instance="ci", data=data, message=self._message(text="menu"))
        await self.dp.feed_update(self.bot, Update(update_id=self._id, callback_query=cb))


@pytest.mark.asyncio
@pytest.mark.parametrize("step", ["waiting_area", "waiting_style", "waiting_wishes"])
async def test_command_in_text_step_leaves_plan_and_reaches_its_handler(env, step):
    await env.set_plan_state(step, area="6")
    await env.text("/price")
    assert env.calls == ["price"]  # команда дошла до своего хендлера, а не ушла ответом анкеты
    assert await env.state() is None
    assert await env.data() == {}


@pytest.mark.asyncio
@pytest.mark.parametrize("step", ALL_STATES)
async def test_menu_main_button_clears_every_plan_state(env, step):
    await env.set_plan_state(step, area="6", style="x")
    await env.button("menu:main")
    assert env.calls == ["menu:main"]
    assert await env.state() is None
    assert await env.data() == {}


@pytest.mark.asyncio
@pytest.mark.parametrize("step", ["waiting_area", "waiting_style", "waiting_wishes"])
async def test_non_text_gets_hint_and_keeps_step(env, step):
    await env.set_plan_state(step, area="6")
    await env.photo()  # раньше: AttributeError на message.text.strip()
    assert await env.state() == getattr(plan.PlanForm, step).state
    assert (await env.data()) == {"area": "6"}
    sent = [p for name, p in env.session.sent if name == "SendMessage"]
    assert sent and sent[-1]["text"] == bot_texts.get("plan")["text_only"]


@pytest.mark.asyncio
async def test_replan_after_unfinished_questionnaire_drops_old_answers(env):
    await env.set_plan_state("waiting_confirm", area="6", style="кантри", budget="до 100к", wishes="старые пожелания")
    await env.text("/plan")
    assert await env.state() == plan.PlanForm.waiting_area.state
    assert await env.data() == {}


@pytest.mark.asyncio
async def test_questionnaire_steps_still_work(env):
    await env.set_plan_state("waiting_area")
    await env.text("6")
    assert await env.state() == plan.PlanForm.waiting_style.state
    await env.text("природный")
    assert await env.state() == plan.PlanForm.waiting_budget.state
    await env.button("budget:до 100к")  # кнопка шага не считается выходом
    assert await env.state() == plan.PlanForm.waiting_wishes.state
    await env.text("нет")
    assert await env.state() == plan.PlanForm.waiting_confirm.state
    assert (await env.data())["budget"] == "до 100к"
    assert env.calls == []  # ничего не ушло в чужие хендлеры


def test_middleware_is_registered_in_bot_py():
    src = (Path(__file__).resolve().parent.parent / "bot.py").read_text(encoding="utf-8")
    assert "dp.message.outer_middleware(PlanExitMiddleware())" in src
    assert "dp.callback_query.outer_middleware(PlanExitMiddleware())" in src


@pytest.mark.asyncio
async def test_other_fsm_flows_are_not_touched(env):
    await env.dp.storage.set_state(env.key, "WateringForm:waiting_time")
    await env.text("/price")
    assert env.calls == ["price"]
    assert await env.state() == "WateringForm:waiting_time"  # не PlanForm: middleware ничего не сбрасывает


@pytest.mark.asyncio
@pytest.mark.parametrize("data", ["nps:5:12", "plan:confirm"])
async def test_nps_and_plan_step_buttons_do_not_leave_plan(env, data):
    await env.set_plan_state("waiting_wishes", area="6")
    await env.button(data)
    assert await env.state() == plan.PlanForm.waiting_wishes.state
    assert await env.data() == {"area": "6"}

def test_leaves_plan_rules():
    """Чистая логика решения «уводит ли событие из анкеты» (в т.ч. /plan@бот и команды с аргументами)."""
    from handlers.plan_exit import leaves_plan

    def msg(text):
        return Message(message_id=1, date=datetime.now(), chat=Chat(id=UID, type="private"), text=text)

    def cb(data):
        return CallbackQuery(id="1", from_user=User(id=UID, is_bot=False, first_name="T"), chat_instance="c", data=data)

    assert leaves_plan(msg("/price"))
    assert leaves_plan(msg("/profile@washsad_ai_bot extra"))
    assert not leaves_plan(msg("/plan"))
    assert not leaves_plan(msg("/plan@washsad_ai_bot"))
    assert not leaves_plan(msg("6"))  # обычный текст — ответ анкеты
    assert leaves_plan(cb("menu:main")) and leaves_plan(cb("menu:price")) and leaves_plan(cb("cancel"))
    assert not leaves_plan(cb("budget:до 100к")) and not leaves_plan(cb("plan:confirm"))
    assert not leaves_plan(cb("nps:5:1"))
