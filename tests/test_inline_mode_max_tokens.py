"""Пункт 1.6 дневного брифа 05.10 (сделан после мержа #61, fix/ai-timeout-except,
в main): handlers/inline_mode.py:53-57 зовёт `ask_claude(..., max_tokens=300)`,
а до этой правки такого параметра не было в сигнатуре `ask_claude` — TypeError
на КАЖДОМ inline-запросе, пойманный `except Exception` в handle_inline —
пользователь inline-режима ВСЕГДА получал "Не удалось получить ответ.
Напишите боту напрямую!", даже когда Claude API в порядке.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.types import InlineQuery

from handlers import inline_mode
from services import ai as ai_module


def _session_cm(resp_text="ok", status=200):
    resp = MagicMock()
    resp.status = status
    resp.text = AsyncMock(return_value=resp_text)
    resp.json = AsyncMock(return_value={"content": [{"text": "Поливайте розы раз в 3-5 дней."}]})

    post_cm = MagicMock()
    post_cm.__aenter__ = AsyncMock(return_value=resp)
    post_cm.__aexit__ = AsyncMock(return_value=False)

    session = MagicMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    session.post = MagicMock(return_value=post_cm)
    return session


def _make_inline_query(text: str) -> MagicMock:
    q = MagicMock(spec=InlineQuery)
    q.query = text
    q.answer = AsyncMock()
    return q


@pytest.mark.asyncio
async def test_inline_query_gets_real_claude_answer_not_fallback():
    """На исправленном ask_claude (с параметром max_tokens) inline-запрос
    доходит до реального ответа Claude, а не до текста-заглушки об ошибке."""
    query = _make_inline_query("Как ухаживать за розами?")
    session = _session_cm()

    with patch.object(ai_module, "ANTHROPIC_API_KEY", "test-key"), \
         patch.object(ai_module.aiohttp, "ClientSession", return_value=session):
        await inline_mode.handle_inline(query)

    query.answer.assert_awaited_once()
    results = query.answer.await_args.args[0]
    text = results[0].input_message_content.message_text
    assert "Не удалось получить ответ" not in text
    assert "Поливайте розы раз в 3-5 дней." in text

    # Сам вызов действительно передавал max_tokens=300, а не был подменён мок-ответом вслепую
    post_call_kwargs = session.post.call_args.kwargs
    assert post_call_kwargs["json"]["max_tokens"] == 300
