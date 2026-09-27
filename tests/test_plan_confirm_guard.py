"""Защита plan:confirm (handlers/plan.py):
1) двойной тап (0 мс и 200 мс) не создаёт вторую заявку и не шлёт второе уведомление;
2) сбой/таймаут ask_claude не создаёт заявку, не шлёт PDF, клиент получает предложение повторить.

Через настоящий Dispatcher + MemoryStorage + реальный роутер плана (как в bot.py), сеть Telegram подменена.
"""
import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from aiogram import Bot, Dispatcher
from aiogram.client.session.base import BaseSession
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, Chat, Message, Update, User

from handlers import plan

UID = 1288492012


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


class SlowSession(FakeSession):
    """Та же фиксация вызовов, но с задержкой сети до Telegram (как реальный callback.answer())."""

    def __init__(self, delay: float):
        super().__init__()
        self.delay = delay

    async def make_request(self, bot, method, timeout=None):
        await asyncio.sleep(self.delay)
        return await super().make_request(bot, method, timeout)


@pytest_asyncio.fixture
async def env():
    dp = Dispatcher(storage=MemoryStorage())  # как в bot.py: без events_isolation
    dp.include_router(plan.router)
    yield dp
    plan.router._parent_router = None


def _make_update(n: int) -> Update:
    user = User(id=UID, is_bot=False, first_name="T")
    msg = Message(message_id=1, date=datetime.now(), chat=Chat(id=UID, type="private"), from_user=user, text="x")
    cb = CallbackQuery(id=str(n), from_user=user, chat_instance="ci", data="plan:confirm", message=msg)
    return Update(update_id=n, callback_query=cb)


async def _prep_waiting_confirm(dp: Dispatcher, bot: Bot):
    key = StorageKey(bot_id=bot.id, chat_id=UID, user_id=UID)
    await dp.storage.set_state(key, plan.PlanForm.waiting_confirm)
    await dp.storage.set_data(key, {"area": "6", "style": "природный", "budget": "до 100к", "wishes": "ТЕСТ"})
    return key


def _patched(ask_claude_result="ПЛАН", save_order_result=31):
    return (
        patch.object(plan, "ask_claude", AsyncMock(return_value=ask_claude_result)),
        patch.object(plan, "save_order", AsyncMock(return_value=save_order_result)),
        patch.object(plan, "get_or_create_user", AsyncMock()),
        patch.object(plan, "_notify_designer", AsyncMock()),
        patch.object(plan, "generate_plan_pdf", MagicMock(return_value=b"%PDF")),
        patch.object(plan, "get_designer_qualification_line", AsyncMock(return_value="q")),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("gap", [0.0, 0.2])
async def test_double_tap_creates_exactly_one_order(env, gap):
    dp = env
    bot = Bot(token="123456:TEST", session=SlowSession(0.05))
    await _prep_waiting_confirm(dp, bot)

    patches = _patched()
    with patches[0], patches[1] as save_order, patches[2], patches[3] as notify, patches[4], patches[5]:
        async def one(i):
            await asyncio.sleep(gap * i)
            await dp.feed_update(bot, _make_update(i + 1))

        await asyncio.gather(one(0), one(1))

    assert save_order.await_count == 1, f"gap={gap}: save_order должен вызваться ровно 1 раз"
    assert notify.await_count == 1, f"gap={gap}: _notify_designer должен вызваться ровно 1 раз"


@pytest.mark.asyncio
async def test_success_creates_order_and_sends_pdf(env):
    """Контроль: обычный (не сбойный, не повторный) confirm по-прежнему создаёт заявку и шлёт PDF."""
    dp = env
    bot = Bot(token="123456:TEST", session=FakeSession())
    await _prep_waiting_confirm(dp, bot)

    patches = _patched(ask_claude_result="🗺 ЗОНИРОВАНИЕ\n...план...")
    with patches[0], patches[1] as save_order, patches[2], patches[3] as notify, patches[4], patches[5]:
        await dp.feed_update(bot, _make_update(1))

    assert save_order.await_count == 1
    assert notify.await_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("error_text", [
    "❌ Ошибка AI. Попробуйте позже или нажмите «Заказать проект» для связи с дизайнером.",
    "⏳ Запрос занял слишком много времени. Попробуйте ещё раз.",
    "⚠️ AI-консультация временно недоступна.\n\n"
    "Для получения совета напишите напрямую дизайнеру — нажмите кнопку «Заказать проект».",
])
async def test_ask_claude_error_does_not_create_order_or_pdf(env, error_text):
    dp = env
    bot = Bot(token="123456:TEST", session=FakeSession())
    await _prep_waiting_confirm(dp, bot)

    patches = _patched(ask_claude_result=error_text)
    with patches[0], patches[1] as save_order, patches[2], patches[3] as notify, patches[4] as gen_pdf, patches[5]:
        await dp.feed_update(bot, _make_update(1))

    assert save_order.await_count == 0, "заявка не должна создаваться при ошибке ask_claude"
    assert notify.await_count == 0, "дизайнер не должен получать уведомление при ошибке ask_claude"
    assert gen_pdf.call_count == 0, "PDF не должен генерироваться из текста ошибки"

    # клиенту ушёл текст-предложение повторить (bot_texts i18n.error_generic), а не текст ошибки Claude
    sent_texts = [
        m.get("text") or ""
        for _, m in bot.session.sent
        if isinstance(m, dict)
    ]
    assert any("Попробуйте ещё раз" in t for t in sent_texts), sent_texts
    assert not any(error_text in t for t in sent_texts if t), "клиент не должен видеть сырой текст ошибки Claude"
