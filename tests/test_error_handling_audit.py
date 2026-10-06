"""Тесты на находки error-handling-audit.md (04.10.2026), пункты 2, 3, 4, 5
(пункт 1 — handlers/errors.py — отдельно в test_global_error_handler.py,
пункт 6/inline-режим вне рамок этого трека, см. отчёт).
"""
import logging
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import asyncpg
import pytest
import pytest_asyncio
from aiogram import Bot, Dispatcher
from aiogram.client.session.base import BaseSession
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, Chat, Message, Update, User

import config
from handlers import plan, promo

FAKE_UID = 100000777  # фиктивный id — не реальный telegram_id


# ── 1.2 handlers/plan.py:287-290 — лог при сбое edit_text (fallback на answer) ──

class _FakeSession(BaseSession):
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


class _SecondEditFailsSession(_FakeSession):
    """_plan_generate делает два edit_text: (1) промежуточное "Составляю план..."
    (должен пройти, иначе до нужной ветки не дойдём) и (2) после ошибки ask_claude —
    именно он должен упасть (как было бы при "message is not modified"/сообщение
    слишком старое для редактирования), чтобы сработал fallback на answer()."""

    def __init__(self):
        super().__init__()
        self._edit_calls = 0

    async def make_request(self, bot, method, timeout=None):
        if type(method).__name__ == "EditMessageText":
            self._edit_calls += 1
            if self._edit_calls >= 2:
                raise TelegramBadRequest(method=method, message="message is not modified")
        return await super().make_request(bot, method, timeout)


@pytest_asyncio.fixture
async def plan_env():
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(plan.router)
    yield dp
    plan.router._parent_router = None


def _plan_confirm_update(n: int, uid: int = FAKE_UID) -> Update:
    user = User(id=uid, is_bot=False, first_name="T")
    msg = Message(message_id=1, date=datetime.now(), chat=Chat(id=uid, type="private"), from_user=user, text="x")
    cb = CallbackQuery(id=str(n), from_user=user, chat_instance="ci", data="plan:confirm", message=msg)
    return Update(update_id=n, callback_query=cb)


@pytest.mark.asyncio
async def test_plan_generate_logs_when_edit_text_fallback_fires(plan_env, caplog):
    dp = plan_env
    bot = Bot(token="123456:TEST", session=_SecondEditFailsSession())
    key = StorageKey(bot_id=bot.id, chat_id=FAKE_UID, user_id=FAKE_UID)
    await dp.storage.set_state(key, plan.PlanForm.waiting_confirm)
    await dp.storage.set_data(key, {"area": "6", "style": "природный", "budget": "до 100к", "wishes": "тест"})

    with patch.object(plan, "ask_claude", AsyncMock(return_value="❌ Ошибка AI. Попробуйте позже.")), \
         caplog.at_level(logging.WARNING, logger="handlers.plan"):
        await dp.feed_update(bot, _plan_confirm_update(1))

    # fallback (answer вместо edit_text) всё равно отправил клиенту текст ошибки
    sent_methods = [m for m, _ in bot.session.sent]
    assert "SendMessage" in sent_methods

    # и при этом в журнал ушла запись о самом сбое edit_text (находка аудита: раньше её не было)
    warnings = [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]
    assert any("edit_text" in w for w in warnings), warnings


# ── 1.3 config.py _int_list_env — предупреждение при нечисловом элементе ──

def test_int_list_env_warns_on_invalid_element(monkeypatch, caplog):
    monkeypatch.setenv("TEST_ID_LIST", "111,abc,222,,333")
    with caplog.at_level(logging.WARNING, logger="config"):
        result = config._int_list_env("TEST_ID_LIST")

    assert result == [111, 222, 333]
    warnings = [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]
    assert any("TEST_ID_LIST" in w and "1" in w for w in warnings), warnings


def test_int_list_env_silent_when_all_valid(caplog):
    # пустая/отсутствующая переменная -> [] без предупреждений (не регрессия)
    with caplog.at_level(logging.WARNING, logger="config"):
        result = config._int_list_env("TEST_ID_LIST_EMPTY_NOT_SET")
    assert result == []
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


# ── 1.4 handlers/promo.py — узкий except только для UniqueViolationError ──

def _mock_pool(execute_side_effect):
    pool = MagicMock()
    conn = AsyncMock()
    conn.execute = AsyncMock(side_effect=execute_side_effect)
    pool.acquire = MagicMock(return_value=AsyncMock(
        __aenter__=AsyncMock(return_value=conn),
        __aexit__=AsyncMock(return_value=False),
    ))
    return pool


def _promo_message(text: str, uid: int = FAKE_UID) -> MagicMock:
    msg = MagicMock()
    msg.text = text
    msg.from_user = MagicMock(id=uid)
    msg.answer = AsyncMock()
    return msg


@pytest.mark.asyncio
async def test_newpromo_duplicate_code_shows_already_exists():
    pool = _mock_pool(asyncpg.exceptions.UniqueViolationError("duplicate key value"))
    message = _promo_message("/newpromo 20 10 TESTCODE")

    with patch.object(promo, "DESIGNER_TELEGRAM_ID", FAKE_UID), \
         patch.object(promo, "get_pool", AsyncMock(return_value=pool)):
        await promo.cmd_new_promo(message)

    text = message.answer.await_args.args[0]
    assert "уже существует" in text


@pytest.mark.asyncio
async def test_newpromo_other_db_error_does_not_claim_duplicate():
    """Находка аудита: раньше любой сбой БД (не только дубликат) показывался
    как «код уже существует» — неверный диагноз. Теперь — честное сообщение."""
    pool = _mock_pool(RuntimeError("connection reset by peer"))
    message = _promo_message("/newpromo 20 10 TESTCODE")

    with patch.object(promo, "DESIGNER_TELEGRAM_ID", FAKE_UID), \
         patch.object(promo, "get_pool", AsyncMock(return_value=pool)):
        await promo.cmd_new_promo(message)

    text = message.answer.await_args.args[0]
    assert "уже существует" not in text
    assert "Не удалось создать код" in text


# ── 1.5 services/scheduler.py — лог вместо pass на TelegramForbiddenError ──

@pytest.mark.asyncio
async def test_send_booking_reminder_logs_when_blocked(caplog):
    from services import scheduler

    pool = MagicMock()
    conn = AsyncMock()
    slot_dt = datetime(2026, 10, 10, 12, 0)
    conn.fetchrow = AsyncMock(return_value={"telegram_id": FAKE_UID, "status": "confirmed", "slot_dt": slot_dt})
    pool.acquire = MagicMock(return_value=AsyncMock(
        __aenter__=AsyncMock(return_value=conn),
        __aexit__=AsyncMock(return_value=False),
    ))

    bot = AsyncMock()
    forbidden = TelegramForbiddenError(MagicMock(), "Forbidden: bot was blocked by the user")
    bot.send_message = AsyncMock(side_effect=forbidden)

    with patch("services.database.get_pool", AsyncMock(return_value=pool)), \
         caplog.at_level(logging.INFO, logger="services.scheduler"):
        await scheduler._send_booking_reminder(bot, 42, slot_dt, "24h")

    infos = [r.getMessage() for r in caplog.records if r.levelno >= logging.INFO]
    assert any("42" in m and ("заблокировал" in m or "blocked" in m.lower()) for m in infos), infos
