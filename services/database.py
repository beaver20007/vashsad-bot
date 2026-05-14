"""
services/database.py
Замена in-memory storage на Neon PostgreSQL (asyncpg).
Полностью совместим с существующим кодом — drop-in замена storage.py
"""
import asyncio
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import asyncpg

log = logging.getLogger(__name__)

# ── Пул соединений (создаётся один раз при старте бота) ──
_pool: asyncpg.Pool | None = None


async def init_db() -> None:
    """Вызвать при старте бота: создаёт пул и таблицы если не существуют."""
    global _pool
    _pool = await asyncpg.create_pool(
        dsn=os.getenv("DATABASE_URL"),
        min_size=1,
        max_size=5,
        statement_cache_size=0,   # обязательно для Neon serverless
    )
    await _create_tables()
    log.info("✅ PostgreSQL подключён (Neon)")


async def close_db() -> None:
    if _pool:
        await _pool.close()


async def _create_tables() -> None:
    async with _pool.acquire() as conn:
        await conn.execute("""
        -- Пользователи
        CREATE TABLE IF NOT EXISTS users (
            telegram_id   BIGINT PRIMARY KEY,
            username      VARCHAR(64),
            first_name    VARCHAR(128),
            region        VARCHAR(128),
            is_subscribed BOOLEAN DEFAULT FALSE,
            chat_count    INTEGER DEFAULT 0,
            photo_count   INTEGER DEFAULT 0,
            plants_count  INTEGER DEFAULT 0,
            plot_size     FLOAT,
            created_at    TIMESTAMP DEFAULT NOW(),
            updated_at    TIMESTAMP DEFAULT NOW()
        );

        -- История AI-чата (отдельная таблица — не в памяти)
        CREATE TABLE IF NOT EXISTS chat_history (
            id          SERIAL PRIMARY KEY,
            telegram_id BIGINT REFERENCES users(telegram_id) ON DELETE CASCADE,
            role        VARCHAR(16) NOT NULL,   -- 'user' | 'assistant'
            content     TEXT NOT NULL,
            created_at  TIMESTAMP DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS idx_chat_history_user
            ON chat_history(telegram_id, created_at DESC);

        -- Заявки / заказы
        CREATE TABLE IF NOT EXISTS orders (
            id           SERIAL PRIMARY KEY,
            telegram_id  BIGINT REFERENCES users(telegram_id),
            service_type VARCHAR(64),
            service_name VARCHAR(128),
            service_price INTEGER,
            area         VARCHAR(64),
            existing     VARCHAR(64),
            style        VARCHAR(64),
            wishes       TEXT,
            phone        VARCHAR(32),
            email        VARCHAR(128),
            status       VARCHAR(32) DEFAULT 'new',
            created_at   TIMESTAMP DEFAULT NOW()
        );

        -- Фото-диагностики
        CREATE TABLE IF NOT EXISTS diagnoses (
            id          SERIAL PRIMARY KEY,
            telegram_id BIGINT REFERENCES users(telegram_id),
            file_id     VARCHAR(256),
            question    TEXT,
            result      TEXT,
            created_at  TIMESTAMP DEFAULT NOW()
        );

        -- Растения пользователя (Мой сад)
        CREATE TABLE IF NOT EXISTS user_plants (
            id          SERIAL PRIMARY KEY,
            telegram_id BIGINT REFERENCES users(telegram_id),
            plant_slug  VARCHAR(64),
            name        VARCHAR(128),
            emoji       VARCHAR(8),
            location    VARCHAR(128),
            planted_at  DATE,
            notes       TEXT,
            added_at    TIMESTAMP DEFAULT NOW()
        );

        -- Избранное каталога
        CREATE TABLE IF NOT EXISTS favorites (
            telegram_id BIGINT REFERENCES users(telegram_id),
            plant_slug  VARCHAR(64),
            PRIMARY KEY (telegram_id, plant_slug)
        );

        -- Задачи по уходу (напоминания)
        CREATE TABLE IF NOT EXISTS garden_tasks (
            id          SERIAL PRIMARY KEY,
            telegram_id BIGINT REFERENCES users(telegram_id),
            plant_id    INTEGER REFERENCES user_plants(id) ON DELETE CASCADE,
            task_type   VARCHAR(32),   -- 'water','fertilize','treat','prune'
            due_date    DATE,
            done        BOOLEAN DEFAULT FALSE,
            created_at  TIMESTAMP DEFAULT NOW()
        );
        """)
    log.info("✅ Таблицы созданы / проверены")


# ══════════════════════════════════════════════════════════════
#  DATACLASS — совместим со старым storage.py
# ══════════════════════════════════════════════════════════════

@dataclass
class User:
    telegram_id: int
    username: Optional[str] = None
    first_name: Optional[str] = None
    region: Optional[str] = None
    is_subscribed: bool = False
    chat_count: int = 0
    photo_count: int = 0
    plants_count: int = 0
    plot_size: Optional[float] = None
    chat_history: list = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)


# ══════════════════════════════════════════════════════════════
#  CRUD — замена функций storage.py
# ══════════════════════════════════════════════════════════════

async def get_or_create_user(
    telegram_id: int,
    username: str = None,
    first_name: str = None,
) -> User:
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM users WHERE telegram_id = $1", telegram_id
        )
        if row is None:
            await conn.execute(
                """INSERT INTO users (telegram_id, username, first_name)
                   VALUES ($1, $2, $3)
                   ON CONFLICT (telegram_id) DO NOTHING""",
                telegram_id, username, first_name,
            )
            row = await conn.fetchrow(
                "SELECT * FROM users WHERE telegram_id = $1", telegram_id
            )
        # Обновляем username/first_name если изменились
        if username and row["username"] != username:
            await conn.execute(
                "UPDATE users SET username=$1, updated_at=NOW() WHERE telegram_id=$2",
                username, telegram_id,
            )
        # Загружаем историю чата
        history_rows = await conn.fetch(
            """SELECT role, content FROM chat_history
               WHERE telegram_id=$1
               ORDER BY created_at DESC LIMIT 20""",
            telegram_id,
        )
        chat_history = [{"role": r["role"], "content": r["content"]}
                        for r in reversed(history_rows)]

    return User(
        telegram_id=row["telegram_id"],
        username=row["username"],
        first_name=row["first_name"],
        region=row["region"],
        is_subscribed=row["is_subscribed"],
        chat_count=row["chat_count"],
        photo_count=row["photo_count"],
        plants_count=row["plants_count"],
        plot_size=row["plot_size"],
        chat_history=chat_history,
        created_at=row["created_at"],
    )


def get_user(telegram_id: int) -> Optional[User]:
    """Синхронная обёртка для совместимости — лучше использовать async версию."""
    loop = asyncio.get_event_loop()
    return loop.run_until_complete(get_or_create_user(telegram_id))


async def update_user(user: User) -> None:
    async with _pool.acquire() as conn:
        await conn.execute(
            """UPDATE users SET
               username=$1, first_name=$2, region=$3,
               is_subscribed=$4, chat_count=$5, photo_count=$6,
               plants_count=$7, plot_size=$8, updated_at=NOW()
               WHERE telegram_id=$9""",
            user.username, user.first_name, user.region,
            user.is_subscribed, user.chat_count, user.photo_count,
            user.plants_count, user.plot_size, user.telegram_id,
        )


# ── Лимиты (совместимо со старым кодом) ──

def can_use_chat(user: User, limit: int) -> bool:
    return user.is_subscribed or user.chat_count < limit


def can_use_photo(user: User, limit: int) -> bool:
    return user.is_subscribed or user.photo_count < limit


def can_use_plants(user: User, limit: int) -> bool:
    return user.is_subscribed or user.plants_count < limit


# ── История чата ──

async def add_message_to_history(
    user: User,
    role: str,
    content: str,
    max_history: int = 10,
) -> None:
    async with _pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO chat_history (telegram_id, role, content) VALUES ($1, $2, $3)",
            user.telegram_id, role, content,
        )
        # Оставляем только последние max_history*2 записей
        await conn.execute(
            """DELETE FROM chat_history
               WHERE telegram_id=$1
               AND id NOT IN (
                   SELECT id FROM chat_history
                   WHERE telegram_id=$1
                   ORDER BY created_at DESC
                   LIMIT $2
               )""",
            user.telegram_id, max_history * 2,
        )
    # Обновляем и в памяти (для текущей сессии)
    user.chat_history.append({"role": role, "content": content})
    if len(user.chat_history) > max_history * 2:
        user.chat_history = user.chat_history[-(max_history * 2):]


# ══════════════════════════════════════════════════════════════
#  ORDERS — сохранение заявок в БД
# ══════════════════════════════════════════════════════════════

async def save_order(
    telegram_id: int,
    service_type: str,
    service_name: str = None,
    service_price: int = None,
    area: str = None,
    existing: str = None,
    style: str = None,
    wishes: str = None,
    phone: str = None,
    email: str = None,
) -> int:
    """Сохранить заявку. Возвращает ID заказа."""
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            """INSERT INTO orders
               (telegram_id, service_type, service_name, service_price,
                area, existing, style, wishes, phone, email)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
               RETURNING id""",
            telegram_id, service_type, service_name, service_price,
            area, existing, style, wishes, phone, email,
        )
    return row["id"]


# ══════════════════════════════════════════════════════════════
#  DIAGNOSES — сохранение диагностик
# ══════════════════════════════════════════════════════════════

async def save_diagnosis(
    telegram_id: int,
    file_id: str,
    question: str,
    result: str,
) -> None:
    async with _pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO diagnoses (telegram_id, file_id, question, result)
               VALUES ($1, $2, $3, $4)""",
            telegram_id, file_id, question, result,
        )


async def get_user_diagnoses(telegram_id: int, limit: int = 10) -> list:
    async with _pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT * FROM diagnoses WHERE telegram_id=$1
               ORDER BY created_at DESC LIMIT $2""",
            telegram_id, limit,
        )
    return [dict(r) for r in rows]


# ══════════════════════════════════════════════════════════════
#  MY GARDEN — растения пользователя
# ══════════════════════════════════════════════════════════════

async def get_user_plants(telegram_id: int) -> list:
    async with _pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM user_plants WHERE telegram_id=$1 ORDER BY added_at DESC",
            telegram_id,
        )
    return [dict(r) for r in rows]


async def add_user_plant(
    telegram_id: int,
    plant_slug: str,
    name: str,
    emoji: str,
    location: str = None,
) -> int:
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            """INSERT INTO user_plants (telegram_id, plant_slug, name, emoji, location)
               VALUES ($1,$2,$3,$4,$5) RETURNING id""",
            telegram_id, plant_slug, name, emoji, location,
        )
    return row["id"]


# ══════════════════════════════════════════════════════════════
#  FAVORITES
# ══════════════════════════════════════════════════════════════

async def toggle_favorite(telegram_id: int, plant_slug: str) -> bool:
    """Добавить/убрать из избранного. Возвращает True если добавлено."""
    async with _pool.acquire() as conn:
        existing = await conn.fetchval(
            "SELECT 1 FROM favorites WHERE telegram_id=$1 AND plant_slug=$2",
            telegram_id, plant_slug,
        )
        if existing:
            await conn.execute(
                "DELETE FROM favorites WHERE telegram_id=$1 AND plant_slug=$2",
                telegram_id, plant_slug,
            )
            return False
        else:
            await conn.execute(
                "INSERT INTO favorites (telegram_id, plant_slug) VALUES ($1,$2)",
                telegram_id, plant_slug,
            )
            return True


async def get_favorites(telegram_id: int) -> list[str]:
    async with _pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT plant_slug FROM favorites WHERE telegram_id=$1",
            telegram_id,
        )
    return [r["plant_slug"] for r in rows]
