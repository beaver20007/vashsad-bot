"""
FastAPI роутер для входящих MAX webhook событий.

Подключить в основном приложении:
    from max_integration.webhook_router import max_router
    app.include_router(max_router)
"""
import hmac
import hashlib
import os
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request
from loguru import logger

from src.platforms.max_platform import MaxPlatform
from src.core.platform import UnifiedMessage, UnifiedCallback

max_router = APIRouter(prefix="/webhook", tags=["MAX"])

# Инициализация платформы (токен из env)
_max_platform: MaxPlatform | None = None


def get_max_platform() -> MaxPlatform:
    global _max_platform
    if _max_platform is None:
        token = os.environ.get("MAX_BOT_TOKEN_VASHSAD", "")
        if not token:
            raise RuntimeError("MAX_BOT_TOKEN_VASHSAD не задан в environment")
        _max_platform = MaxPlatform(token=token)
    return _max_platform


@max_router.post("/max")
async def max_webhook(request: Request) -> dict[str, str]:
    """
    Обработчик входящих событий от MAX.

    MAX отправляет HTTPS POST с JSON payload.
    Структура: {"update_type": "...", "user_locale": "...", <данные>}
    """
    try:
        payload: dict[str, Any] = await request.json()
    except Exception as e:
        logger.error("MAX webhook: невалидный JSON: {e}", e=e)
        raise HTTPException(status_code=400, detail="Invalid JSON")

    # Логируем сырой payload — это критично для дебага
    logger.debug("MAX webhook received: {payload}", payload=payload)

    platform = get_max_platform()
    event = MaxPlatform.parse_webhook(payload)

    if event is None:
        # Неизвестный тип события — принимаем, не падаем
        return {"status": "ignored"}

    if isinstance(event, UnifiedMessage):
        await handle_message(event, platform)
    elif isinstance(event, UnifiedCallback):
        await handle_callback(event, platform)

    return {"status": "ok"}


async def handle_message(msg: UnifiedMessage, platform: MaxPlatform) -> None:
    """Диспетчер входящих сообщений."""
    text = (msg.text or "").strip()
    logger.info(
        "MAX message from {uid}: {text}",
        uid=msg.user.platform_id,
        text=text[:100],
    )

    if text == "/start" or text == "bot_started":
        await platform.send_message(
            chat_id=msg.chat_id,
            text=(
                f"Привет, {msg.user.first_name}! 🌿\n\n"
                "Я бот сервиса ВашСад.\n"
                "Помогу с записью на консультацию и вопросами по уходу за садом."
            ),
        )
        return

    if text == "/help":
        await platform.send_message(
            chat_id=msg.chat_id,
            text="Доступные команды:\n/start — начало\n/catalog — каталог растений\n/order — записаться",
        )
        return

    # TODO: подключить FSM из основного проекта ВашСад
    await platform.send_message(
        chat_id=msg.chat_id,
        text="Команда в разработке. Напишите /help для списка команд.",
    )


async def handle_callback(cb: UnifiedCallback, platform: MaxPlatform) -> None:
    """Диспетчер callback от inline-кнопок."""
    logger.info(
        "MAX callback from {uid}: {data}",
        uid=cb.user.platform_id,
        data=cb.data,
    )
    # Сначала всегда отвечаем на callback (убираем часики)
    await platform.answer_callback(cb.callback_id)

    # TODO: подключить обработчики из основного проекта
    await platform.send_message(
        chat_id=cb.chat_id,
        text=f"Получен callback: {cb.data}",
    )
