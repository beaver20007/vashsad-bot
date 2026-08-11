"""Фаза 5: Блокировка и whitelist пользователей"""
import logging
from aiogram import Router, BaseMiddleware
from aiogram.filters import Command
from aiogram.types import Message, TelegramObject
from typing import Any, Awaitable, Callable

from config import DESIGNER_TELEGRAM_ID
from services.database import get_pool

router = Router()
log = logging.getLogger(__name__)


async def create_moderation_tables():
    async with get_pool().acquire() as conn:
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
            async with get_pool().acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT is_banned FROM users WHERE telegram_id=$1", user.id
                )
            if row and row["is_banned"]:
                return  # тихий игнор
        return await handler(event, data)


@router.message(Command("ban"))
async def cmd_ban(message: Message):
    if message.from_user.id != DESIGNER_TELEGRAM_ID:
        return
    parts = message.text.split(maxsplit=2)
    if len(parts) < 2:
        await message.answer("Формат: <code>/ban USER_ID [причина]</code>", parse_mode="HTML")
        return
    try:
        target_id = int(parts[1])
    except ValueError:
        await message.answer("USER_ID должен быть числом.")
        return
    reason = parts[2] if len(parts) > 2 else "нет причины"

    async with get_pool().acquire() as conn:
        await conn.execute(
            "UPDATE users SET is_banned=TRUE WHERE telegram_id=$1", target_id
        )
        await conn.execute(
            "INSERT INTO ban_log (telegram_id, action, reason, by_admin) VALUES ($1,'ban',$2,$3)",
            target_id, reason, message.from_user.id,
        )
    await message.answer(f"🚫 Пользователь {target_id} заблокирован. Причина: {reason}")


@router.message(Command("unban"))
async def cmd_unban(message: Message):
    if message.from_user.id != DESIGNER_TELEGRAM_ID:
        return
    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("Формат: <code>/unban USER_ID</code>", parse_mode="HTML")
        return
    try:
        target_id = int(parts[1])
    except ValueError:
        await message.answer("USER_ID должен быть числом.")
        return

    async with get_pool().acquire() as conn:
        await conn.execute(
            "UPDATE users SET is_banned=FALSE WHERE telegram_id=$1", target_id
        )
        await conn.execute(
            "INSERT INTO ban_log (telegram_id, action, by_admin) VALUES ($1,'unban',$2)",
            target_id, message.from_user.id,
        )
    await message.answer(f"✅ Пользователь {target_id} разблокирован.")


@router.message(Command("whitelist"))
async def cmd_whitelist(message: Message):
    if message.from_user.id != DESIGNER_TELEGRAM_ID:
        return
    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("Формат: <code>/whitelist USER_ID</code>", parse_mode="HTML")
        return
    try:
        target_id = int(parts[1])
    except ValueError:
        await message.answer("USER_ID должен быть числом.")
        return

    async with _pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET is_whitelist=TRUE WHERE telegram_id=$1", target_id
        )
        await conn.execute(
            "INSERT INTO ban_log (telegram_id, action, by_admin) VALUES ($1,'whitelist',$2)",
            target_id, message.from_user.id,
        )
    await message.answer(f"⭐ Пользователь {target_id} добавлен в whitelist.")


@router.message(Command("bans"))
async def cmd_bans(message: Message):
    if message.from_user.id != DESIGNER_TELEGRAM_ID:
        return
    async with get_pool().acquire() as conn:
        rows = await conn.fetch(
            """SELECT u.telegram_id, u.first_name, u.username, u.is_banned, u.is_whitelist
               FROM users u WHERE u.is_banned=TRUE OR u.is_whitelist=TRUE
               ORDER BY u.created_at DESC LIMIT 20"""
        )
    if not rows:
        await message.answer("Нет заблокированных или whitelist-пользователей.")
        return
    lines = []
    for r in rows:
        status = "🚫" if r["is_banned"] else "⭐"
        lines.append(f"{status} {r['first_name'] or '—'} (@{r['username'] or '—'}) · {r['telegram_id']}")
    await message.answer(
        "<b>Пользователи с особым статусом:</b>\n\n" + "\n".join(lines),
        parse_mode="HTML",
    )
