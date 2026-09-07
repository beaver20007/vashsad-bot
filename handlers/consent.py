"""152-ФЗ: middleware, требующий согласия на обработку ПДн до использования бота.

Гейт применяется глобально (все Message/CallbackQuery), кроме самой команды
/start (она показывает экран согласия) и callback кнопки подтверждения —
см. handlers/start.py::cb_pdn_consent_start.
"""
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from services.database import get_pool

log = logging.getLogger(__name__)

_CONSENT_CALLBACK = "pdn:consent_start"


class PdnConsentMiddleware(BaseMiddleware):
    """Блокирует хендлеры бота, пока пользователь не подтвердил согласие на обработку ПДн."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        if not user:
            return await handler(event, data)

        if isinstance(event, Message):
            first_word = (event.text or "").split(maxsplit=1)[:1]
            if first_word and first_word[0].split("@")[0] == "/start":
                return await handler(event, data)
        elif isinstance(event, CallbackQuery):
            if event.data == _CONSENT_CALLBACK:
                return await handler(event, data)

        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT pdn_consent_at FROM users WHERE telegram_id=$1", user.id
            )

        if row is None or row["pdn_consent_at"] is None:
            from config import DESIGNER_NAME_GEN
            from handlers.start import PDN_CONSENT_TEXT, pdn_consent_keyboard

            text = PDN_CONSENT_TEXT.format(designer_name=DESIGNER_NAME_GEN)
            if isinstance(event, Message):
                await event.answer(text, reply_markup=pdn_consent_keyboard(), parse_mode="HTML")
            elif isinstance(event, CallbackQuery):
                await event.answer(
                    "Сначала подтвердите согласие на обработку ПДн — отправьте /start",
                    show_alert=True,
                )
            return  # не пускаем дальше

        return await handler(event, data)
