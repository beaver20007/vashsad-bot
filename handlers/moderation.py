"""Фаза 5: Блокировка и whitelist пользователей.

Команды /ban /unban /whitelist /bans убраны треком cleanup-admin-dupes
(2026-08-21) — живут только в admin_bot (handlers/admin_bot_handlers.py),
подтверждённо рабочем в проде. BanCheckMiddleware и create_moderation_tables()
остались — это инфраструктура основного бота (принудительное применение
бана к реальным пользователям), не дублирующая admin-команда.
"""
import logging
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from typing import Any, Awaitable, Callable

from services.database import get_pool

log = logging.getLogger(__name__)


async def create_moderation_tables():
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
        ALTER TABLE users ADD COLUMN IF NOT EXISTS is_banned BOOLEAN DEFAULT FALSE;
        ALTER TABLE users ADD COLUMN IF NOT EXISTS is_whitelist BOOLEAN DEFAULT FALSE;
        CREATE TABLE IF NOT EXISTS ban_log (
            id          SERIAL PRIMARY KEY,
            telegram_id BIGINT,
            action      VARCHAR(16),   -- 'ban' | 'unban' | 'whitelist'
            reason      TEXT,
            by_admin    BIGINT,
            created_at  TIMESTAMP DEFAULT NOW()
        );
        """)


class BanCheckMiddleware(BaseMiddleware):
    """Middleware: тихо блокирует забаненных пользователей."""
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        if user:
            pool = await get_pool()
            async with pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT is_banned FROM users WHERE telegram_id=$1", user.id
                )
            if row and row["is_banned"]:
                return  # тихий игнор
        return await handler(event, data)
