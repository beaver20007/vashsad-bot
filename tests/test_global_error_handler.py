"""handlers/errors.py — глобальный обработчик необработанных исключений
(error-handling-audit.md, 04.10.2026, пункт 3: без него пользователь не
получает вообще никакого ответа при сбое). Модуль новый — на origin/main
(до этого трека) его нет вообще, импорт ниже падает ImportError/ModuleNotFoundError
на старом коде (это и есть "падает на старом коде" для всего файла)."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from handlers.errors import global_error_handler

FAKE_USER_ID = 100000055


def _event(exception, with_message=False, with_callback=False, user_id=FAKE_USER_ID):
    update = MagicMock()
    update.event_type = "message" if with_message else "callback_query"
    update.message = None
    update.callback_query = None
    update.inline_query = None

    if with_message:
        msg = MagicMock()
        msg.from_user = MagicMock(id=user_id)
        msg.answer = AsyncMock()
        update.message = msg
    if with_callback:
        cb = MagicMock()
        cb.from_user = MagicMock(id=user_id)
        cb.answer = AsyncMock()
        update.callback_query = cb

    event = MagicMock()
    event.update = update
    event.exception = exception
    return event


@pytest.mark.asyncio
async def test_message_update_gets_error_generic_reply():
    event = _event(ValueError("boom"), with_message=True)
    result = await global_error_handler(event)
    event.update.message.answer.assert_awaited_once()
    text = event.update.message.answer.await_args.args[0]
    assert "❌" in text or "пошло не так" in text.lower()
    assert result is not None


@pytest.mark.asyncio
async def test_callback_update_gets_error_generic_answer():
    event = _event(RuntimeError("boom"), with_callback=True)
    await global_error_handler(event)
    event.update.callback_query.answer.assert_awaited_once()
    args, kwargs = event.update.callback_query.answer.await_args
    assert args[0] or kwargs.get("text")


@pytest.mark.asyncio
async def test_handler_never_raises_even_if_reply_itself_fails():
    event = _event(ValueError("boom"), with_message=True)
    event.update.message.answer = AsyncMock(side_effect=RuntimeError("telegram недоступен"))
    # не должно бросить исключение наружу — иначе сам стал бы вторым необработанным сбоем
    await global_error_handler(event)


@pytest.mark.asyncio
async def test_log_masks_user_id(caplog):
    event = _event(ValueError("boom"), with_message=True, user_id=FAKE_USER_ID)
    with caplog.at_level("ERROR"):
        await global_error_handler(event)
    full_id = str(FAKE_USER_ID)
    joined = "\n".join(r.getMessage() for r in caplog.records)
    assert full_id not in joined, "полный telegram_id не должен попадать в журнал"
    assert full_id[-2:] in joined, "последние 2 цифры id ожидаются в журнале (маска ***NN)"
    assert "ValueError" in joined
