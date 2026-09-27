"""/crosspost в админ-боте: Аня отправляет текст поста, он передаётся в
send_crosspost() (services/loomy_crosspost.py). Сама отправка на n8n-вебхук
LOOMY НЕ реализована (формат заголовка/секрета ещё не согласован с Чатом
LOOMY) — send_crosspost() сейчас всегда бросает LoomyCrosspostNotConfigured,
и это явно проверяется тестами ниже, а не подразумевается.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.loomy_crosspost import LoomyCrosspostNotConfigured, send_crosspost


def _make_message(text: str, user_id: int = 1288492012) -> MagicMock:
    msg = MagicMock()
    msg.text = text
    msg.from_user = SimpleNamespace(id=user_id, username="anya", first_name="Аня")
    msg.answer = AsyncMock()
    return msg


@pytest.mark.asyncio
async def test_send_crosspost_is_not_configured_yet():
    """Пока формат не согласован с LOOMY — функция ничего не отправляет и явно об этом сообщает."""
    with pytest.raises(LoomyCrosspostNotConfigured):
        await send_crosspost("текст поста")


@pytest.mark.asyncio
async def test_crosspost_start_requires_admin():
    from handlers import admin_bot_handlers as h

    message = _make_message("/crosspost")
    with patch.object(h, "is_admin", AsyncMock(return_value=False)):
        await h.cmd_crosspost_start(message)

    message.answer.assert_not_awaited()
    assert message.from_user.id not in h._pending_crossposts


@pytest.mark.asyncio
async def test_crosspost_start_sets_pending_for_admin():
    from handlers import admin_bot_handlers as h

    message = _make_message("/crosspost")
    with patch.object(h, "is_admin", AsyncMock(return_value=True)):
        await h.cmd_crosspost_start(message)

    assert message.from_user.id in h._pending_crossposts
    message.answer.assert_awaited_once()
    assert "Кросс-постинг" in message.answer.await_args.args[0]

    h._pending_crossposts.discard(message.from_user.id)


@pytest.mark.asyncio
async def test_cancel_crosspost_clears_pending():
    from handlers import admin_bot_handlers as h

    message = _make_message("/cancel_crosspost")
    h._pending_crossposts.add(message.from_user.id)

    await h.cmd_cancel_crosspost(message)

    assert message.from_user.id not in h._pending_crossposts
    message.answer.assert_awaited_once_with("❌ Кросс-постинг отменён.")


@pytest.mark.asyncio
async def test_receive_crosspost_text_not_configured_tells_anya_and_does_not_lose_flow():
    from handlers import admin_bot_handlers as h

    message = _make_message("Новый пост про мульчирование")
    h._pending_crossposts.add(message.from_user.id)

    with patch.object(h, "is_admin", AsyncMock(return_value=True)):
        await h.receive_crosspost_text(message)

    assert message.from_user.id not in h._pending_crossposts  # снят из ожидания, не завис
    message.answer.assert_awaited_once()
    sent = message.answer.await_args.args[0]
    assert "принят" in sent.lower()
    assert "не настроена" in sent.lower()


@pytest.mark.asyncio
async def test_receive_crosspost_text_empty_is_rejected_without_calling_send():
    from handlers import admin_bot_handlers as h

    message = _make_message("   ")
    h._pending_crossposts.add(message.from_user.id)

    with patch.object(h, "is_admin", AsyncMock(return_value=True)), \
         patch.object(h, "send_crosspost", AsyncMock()) as mock_send:
        await h.receive_crosspost_text(message)

    mock_send.assert_not_awaited()
    assert "Пустой текст" in message.answer.await_args.args[0]


@pytest.mark.asyncio
async def test_receive_crosspost_text_success_path_once_configured():
    """Когда send_crosspost когда-нибудь заработает (замокано) — Аня получает подтверждение отправки."""
    from handlers import admin_bot_handlers as h

    message = _make_message("Текст поста")
    h._pending_crossposts.add(message.from_user.id)

    with patch.object(h, "is_admin", AsyncMock(return_value=True)), \
         patch.object(h, "send_crosspost", AsyncMock()) as mock_send:
        await h.receive_crosspost_text(message)

    mock_send.assert_awaited_once_with("Текст поста")
    message.answer.assert_awaited_once_with("✅ Отправлено в LOOMY.")


@pytest.mark.asyncio
async def test_receive_crosspost_text_requires_admin():
    from handlers import admin_bot_handlers as h

    message = _make_message("Текст поста")
    h._pending_crossposts.add(message.from_user.id)

    with patch.object(h, "is_admin", AsyncMock(return_value=False)), \
         patch.object(h, "send_crosspost", AsyncMock()) as mock_send:
        await h.receive_crosspost_text(message)

    mock_send.assert_not_awaited()
    message.answer.assert_not_awaited()
