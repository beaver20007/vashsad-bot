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


async def get_pool() -> asyncpg.Pool:
    """Вернуть активный пул соединений. Используется хэндлерами напрямую."""
    if _pool is None:
        raise RuntimeError("Database pool not initialised. Call init_db() first.")
    return _pool


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

        -- Аналитика A/B тестов и событий
        CREATE TABLE IF NOT EXISTS analytics_events (
            id          SERIAL PRIMARY KEY,
            telegram_id BIGINT,
            event_name  VARCHAR(64) NOT NULL,
            params      JSONB DEFAULT '{}',
            created_at  TIMESTAMP DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS idx_analytics_events_name
            ON analytics_events(event_name, created_at DESC);

        -- Платежи YooKassa
        CREATE TABLE IF NOT EXISTS payments (
            id              SERIAL PRIMARY KEY,
            telegram_id     BIGINT REFERENCES users(telegram_id),
            yookassa_id     VARCHAR(64) UNIQUE,
            amount          INTEGER NOT NULL,
            description     TEXT,
            status          VARCHAR(32) DEFAULT 'pending',
            plan            VARCHAR(32),
            created_at      TIMESTAMP DEFAULT NOW(),
            updated_at      TIMESTAMP DEFAULT NOW()
        );

        -- Напоминания о поливе
        CREATE TABLE IF NOT EXISTS watering_reminders (
            id             SERIAL PRIMARY KEY,
            telegram_id    BIGINT NOT NULL,
            plants         TEXT NOT NULL,
            reminder_time  TIME NOT NULL,
            frequency      VARCHAR(20) NOT NULL,
            active         BOOLEAN DEFAULT TRUE,
            created_at     TIMESTAMP DEFAULT NOW()
        );

        -- Ответы на опросы (растение сезона)
        CREATE TABLE IF NOT EXISTS poll_answers (
            id          SERIAL PRIMARY KEY,
            telegram_id BIGINT,
            poll_id     VARCHAR(64),
            option_id   INTEGER NOT NULL,
            created_at  TIMESTAMP DEFAULT NOW()
        );

        -- Подписки на рассылку
        CREATE TABLE IF NOT EXISTS newsletter_subscriptions (
            id          SERIAL PRIMARY KEY,
            telegram_id BIGINT REFERENCES users(telegram_id) ON DELETE CASCADE,
            topics      TEXT DEFAULT 'general',
            active      BOOLEAN DEFAULT TRUE,
            created_at  TIMESTAMP DEFAULT NOW(),
            UNIQUE(telegram_id)
        );
        """)

    # Добавляем новые поля к users если их нет (ALTER TABLE IF NOT EXISTS колонка)
    async with _pool.acquire() as conn:
        for col_sql in [
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS subscription_expires_at TIMESTAMP",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS referral_code VARCHAR(12) UNIQUE",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS referred_by BIGINT REFERENCES users(telegram_id)",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS bonus_messages INTEGER DEFAULT 0",
        ]:
            await conn.execute(col_sql)
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
    subscription_expires_at: Optional[datetime] = None
    referral_code: Optional[str] = None
    referred_by: Optional[int] = None
    bonus_messages: int = 0


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
        subscription_expires_at=row.get("subscription_expires_at"),
        referral_code=row.get("referral_code"),
        referred_by=row.get("referred_by"),
        bonus_messages=row.get("bonus_messages") or 0,
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
    return user.is_subscribed or user.chat_count < (limit + user.bonus_messages)


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


# ══════════════════════════════════════════════════════════════
#  REFERRAL — реферальная программа
# ══════════════════════════════════════════════════════════════

def _make_referral_code(telegram_id: int) -> str:
    """REF + base36 от telegram_id, до 10 символов."""
    alphabet = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    n, code = abs(telegram_id), ""
    while n:
        n, rem = divmod(n, 36)
        code = alphabet[rem] + code
    return "REF" + (code or "0")[:7]


async def get_or_create_referral_code(telegram_id: int) -> str:
    async with _pool.acquire() as conn:
        existing = await conn.fetchval(
            "SELECT referral_code FROM users WHERE telegram_id=$1", telegram_id
        )
        if existing:
            return existing
        code = _make_referral_code(telegram_id)
        await conn.execute(
            "UPDATE users SET referral_code=$1 WHERE telegram_id=$2",
            code, telegram_id,
        )
        return code


async def apply_referral(new_user_id: int, referral_code: str) -> bool:
    """Применить реферальный код при /start. Возвращает True если засчитан."""
    async with _pool.acquire() as conn:
        # Ищем пригласившего
        referrer = await conn.fetchrow(
            "SELECT telegram_id FROM users WHERE referral_code=$1", referral_code
        )
        if not referrer or referrer["telegram_id"] == new_user_id:
            return False
        # Проверяем что новый пользователь ещё не привязан
        already = await conn.fetchval(
            "SELECT referred_by FROM users WHERE telegram_id=$1", new_user_id
        )
        if already:
            return False
        referrer_id = referrer["telegram_id"]
        # Новому пользователю — +3 бонусных сообщения + пометка кто пригласил
        await conn.execute(
            """UPDATE users SET referred_by=$1, bonus_messages=bonus_messages+3
               WHERE telegram_id=$2""",
            referrer_id, new_user_id,
        )
        # Пригласившему — +3 бонусных сообщения
        await conn.execute(
            "UPDATE users SET bonus_messages=bonus_messages+3 WHERE telegram_id=$1",
            referrer_id,
        )
        return True


async def get_referral_stats(telegram_id: int) -> dict:
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT referral_code, bonus_messages FROM users WHERE telegram_id=$1",
            telegram_id,
        )
        invited = await conn.fetchval(
            "SELECT COUNT(*) FROM users WHERE referred_by=$1", telegram_id
        )
    return {
        "referral_code": row["referral_code"] if row else None,
        "bonus_messages": row["bonus_messages"] if row else 0,
        "invited_count": invited or 0,
    }


# ══════════════════════════════════════════════════════════════
#  PAYMENTS — YooKassa
# ══════════════════════════════════════════════════════════════

async def save_payment(
    telegram_id: int,
    yookassa_id: str,
    amount: int,
    description: str,
    plan: str,
) -> int:
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            """INSERT INTO payments (telegram_id, yookassa_id, amount, description, plan)
               VALUES ($1,$2,$3,$4,$5) RETURNING id""",
            telegram_id, yookassa_id, amount, description, plan,
        )
    return row["id"]


async def get_payment_by_yookassa_id(yookassa_id: str) -> Optional[dict]:
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM payments WHERE yookassa_id=$1", yookassa_id
        )
    return dict(row) if row else None


async def mark_payment_succeeded(yookassa_id: str) -> Optional[int]:
    """Отметить платёж как успешный. Возвращает telegram_id."""
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            """UPDATE payments SET status='succeeded', updated_at=NOW()
               WHERE yookassa_id=$1 RETURNING telegram_id, plan""",
            yookassa_id,
        )
    return row if row else None


async def activate_subscription(telegram_id: int, months: int) -> None:
    async with _pool.acquire() as conn:
        await conn.execute(
            """UPDATE users SET
               is_subscribed=TRUE,
               subscription_expires_at=NOW() + ($1 * INTERVAL '1 month'),
               updated_at=NOW()
               WHERE telegram_id=$2""",
            months, telegram_id,
        )


# ══════════════════════════════════════════════════════════════
#  DESIGNER STATS — статистика для дизайнера
# ══════════════════════════════════════════════════════════════

async def get_designer_stats() -> dict:
    async with _pool.acquire() as conn:
        total_users = await conn.fetchval("SELECT COUNT(*) FROM users")
        new_7d = await conn.fetchval(
            "SELECT COUNT(*) FROM users WHERE created_at >= NOW() - INTERVAL '7 days'"
        )
        new_30d = await conn.fetchval(
            "SELECT COUNT(*) FROM users WHERE created_at >= NOW() - INTERVAL '30 days'"
        )
        subscribed = await conn.fetchval(
            "SELECT COUNT(*) FROM users WHERE is_subscribed=TRUE"
        )
        total_orders = await conn.fetchval("SELECT COUNT(*) FROM orders")
        orders_7d = await conn.fetchval(
            "SELECT COUNT(*) FROM orders WHERE created_at >= NOW() - INTERVAL '7 days'"
        )
        revenue = await conn.fetchval(
            "SELECT COALESCE(SUM(service_price),0) FROM orders WHERE service_price IS NOT NULL"
        ) or 0
        top_services = await conn.fetch(
            """SELECT service_name, COUNT(*) as cnt
               FROM orders WHERE service_name IS NOT NULL
               GROUP BY service_name ORDER BY cnt DESC LIMIT 3"""
        )
        recent_orders = await conn.fetch(
            """SELECT service_name, phone, first_name, created_at
               FROM orders o JOIN users u ON o.telegram_id=u.telegram_id
               ORDER BY o.created_at DESC LIMIT 5"""
        )
    return {
        "total_users": total_users,
        "new_7d": new_7d,
        "new_30d": new_30d,
        "subscribed": subscribed,
        "total_orders": total_orders,
        "orders_7d": orders_7d,
        "revenue": revenue,
        "top_services": [dict(r) for r in top_services],
        "recent_orders": [dict(r) for r in recent_orders],
    }


# ══════════════════════════════════════════════════════════════
#  BROADCAST — для сезонных рассылок
# ══════════════════════════════════════════════════════════════

async def update_user_region(telegram_id: int, region: str) -> None:
    """Сохранить регион пользователя."""
    async with _pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET region=$1, updated_at=NOW() WHERE telegram_id=$2",
            region, telegram_id,
        )


async def get_all_user_ids() -> list[int]:
    async with _pool.acquire() as conn:
        rows = await conn.fetch("SELECT telegram_id FROM users")
    return [r["telegram_id"] for r in rows]


# ══════════════════════════════════════════════════════════════
#  NOTIFICATIONS — лог рассылок
# ══════════════════════════════════════════════════════════════

async def create_notification_log_table() -> None:
    async with _pool.acquire() as conn:
        await conn.execute("""CREATE TABLE IF NOT EXISTS notification_log (
            id SERIAL PRIMARY KEY,
            telegram_id BIGINT,
            message_type VARCHAR(64),
            sent_at TIMESTAMP DEFAULT NOW()
        )"""
        )


async def log_notification(telegram_id: int, message_type: str) -> None:
    async with _pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO notification_log (telegram_id, message_type) VALUES ($1,$2)",
            telegram_id, message_type,
        )


# ══════════════════════════════════════════════════════════════
#  GARDEN TASKS — задачи по уходу за растениями
# ══════════════════════════════════════════════════════════════

async def get_garden_tasks(telegram_id: int, limit: int = 20) -> list:
    """Get upcoming garden tasks for a user."""
    async with _pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT gt.*, up.name as plant_name, up.emoji as plant_emoji
               FROM garden_tasks gt
               JOIN user_plants up ON gt.plant_id = up.id
               WHERE gt.telegram_id=$1 AND gt.done=FALSE
               ORDER BY gt.due_date ASC LIMIT $2""",
            telegram_id, limit,
        )
    return [dict(r) for r in rows]


async def create_garden_task(telegram_id: int, plant_id: int, task_type: str, due_date) -> int:
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            """INSERT INTO garden_tasks (telegram_id, plant_id, task_type, due_date)
               VALUES ($1,$2,$3,$4) RETURNING id""",
            telegram_id, plant_id, task_type, due_date,
        )
    return row["id"]


async def mark_task_done(task_id: int) -> None:
    async with _pool.acquire() as conn:
        await conn.execute("UPDATE garden_tasks SET done=TRUE WHERE id=$1", task_id)


async def get_users_with_tasks_due_today() -> list:
    async with _pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT DISTINCT gt.telegram_id, u.first_name
               FROM garden_tasks gt JOIN users u ON gt.telegram_id=u.telegram_id
               WHERE gt.due_date=CURRENT_DATE AND gt.done=FALSE"""
        )
    return [dict(r) for r in rows]


# ══════════════════════════════════════════════════════════════
#  ANALYTICS EVENTS — A/B тест и конверсии
# ══════════════════════════════════════════════════════════════

import json as _json


async def insert_analytics_event(
    telegram_id: int,
    event_name: str,
    params: dict | None = None,
) -> None:
    """Записать аналитическое событие (A/B тест, конверсия и т.д.)."""
    async with _pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO analytics_events (telegram_id, event_name, params)
               VALUES ($1, $2, $3::jsonb)""",
            telegram_id,
            event_name,
            _json.dumps(params or {}),
        )


async def update_order_status(order_id: int, status: str) -> Optional[dict]:
    """Обновить статус заявки. Возвращает dict с telegram_id, service_name, service_type или None."""
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            """UPDATE orders SET status=$1, updated_at=NOW()
               WHERE id=$2
               RETURNING id, telegram_id, service_type, service_name, status""",
            status, order_id,
        )
    return dict(row) if row else None


async def get_ab_stats() -> list[dict]:
    """Статистика A/B теста: старты и конверсии по вариантам."""
    async with _pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT
                   params->>'ab_variant' AS variant,
                   COUNT(*) AS starts,
                   SUM(CASE WHEN event_name='order_placed' THEN 1 ELSE 0 END) AS orders
               FROM analytics_events
               WHERE params->>'ab_variant' IS NOT NULL
               GROUP BY params->>'ab_variant'
               ORDER BY variant"""
        )
    return [dict(r) for r in rows]
