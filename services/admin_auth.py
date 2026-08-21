"""Доступ к админ-боту: таблица admin_users вместо жёсткого DESIGNER_TELEGRAM_ID."""
import logging

from services.database import get_pool

log = logging.getLogger(__name__)


async def create_admin_users_table() -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS admin_users (
            telegram_id BIGINT PRIMARY KEY,
            name        VARCHAR(128),
            role        VARCHAR(16) NOT NULL DEFAULT 'team',  -- 'owner' | 'team'
            added_at    TIMESTAMP DEFAULT NOW()
        );
        """)


async def ensure_order_reply_column() -> None:
    """orders.replied — отдельно от status: "ответили клиенту хотя бы раз",
    не смешивается со статусом заявки (new/in_progress/review/done/canceled),
    который остаётся клиентским жизненным циклом. Нужно для фильтра
    "Отвечено" в /orders админ-бота (трек admin-bot-layer-a-workflow)."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "ALTER TABLE orders ADD COLUMN IF NOT EXISTS replied BOOLEAN DEFAULT FALSE"
        )


async def is_admin(telegram_id: int) -> bool:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT 1 FROM admin_users WHERE telegram_id=$1", telegram_id
        )
    return row is not None


async def get_admin_role(telegram_id: int) -> str | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT role FROM admin_users WHERE telegram_id=$1", telegram_id
        )
    return row["role"] if row else None


async def is_owner(telegram_id: int) -> bool:
    return await get_admin_role(telegram_id) == "owner"


async def admin_table_empty() -> bool:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT 1 FROM admin_users LIMIT 1")
    return row is None


async def add_admin(telegram_id: int, name: str, role: str) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO admin_users (telegram_id, name, role)
               VALUES ($1, $2, $3)
               ON CONFLICT (telegram_id) DO UPDATE SET name=$2, role=$3""",
            telegram_id, name, role,
        )


async def list_admins() -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT telegram_id, name, role, added_at FROM admin_users ORDER BY added_at"
        )
    return [dict(r) for r in rows]
