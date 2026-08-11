"""Фаза 2: Промокоды — скидки для пользователей"""
import logging
import secrets
import string
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import DESIGNER_TELEGRAM_ID
from services.database import get_pool

router = Router()
log = logging.getLogger(__name__)


def _gen_code(length: int = 8) -> str:
    chars = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(chars) for _ in range(length))


async def create_promo_table():
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS promo_codes (
            id           SERIAL PRIMARY KEY,
            code         VARCHAR(16) UNIQUE,
            discount_pct INTEGER NOT NULL,
            uses_left    INTEGER DEFAULT 1,
            expires_at   TIMESTAMP,
            created_at   TIMESTAMP DEFAULT NOW()
        );
        CREATE TABLE IF NOT EXISTS promo_uses (
            id           SERIAL PRIMARY KEY,
            promo_id     INTEGER REFERENCES promo_codes(id),
            telegram_id  BIGINT REFERENCES users(telegram_id),
            used_at      TIMESTAMP DEFAULT NOW(),
            UNIQUE (promo_id, telegram_id)
        );
        """)


async def apply_promo(telegram_id: int, code: str) -> dict:
    """
    Применяет промокод. Возвращает:
    {'ok': True, 'discount': 20} или {'ok': False, 'reason': '...'}
    """
    code = code.strip().upper()
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """SELECT id, discount_pct, uses_left, expires_at
               FROM promo_codes WHERE code=$1""", code
        )
        if not row:
            return {"ok": False, "reason": "Промокод не найден"}
        if row["uses_left"] <= 0:
            return {"ok": False, "reason": "Промокод исчерпан"}
        from datetime import datetime
        if row["expires_at"] and row["expires_at"] < datetime.now():
            return {"ok": False, "reason": "Промокод истёк"}

        already = await conn.fetchval(
            "SELECT 1 FROM promo_uses WHERE promo_id=$1 AND telegram_id=$2",
            row["id"], telegram_id,
        )
        if already:
            return {"ok": False, "reason": "Вы уже использовали этот промокод"}

        await conn.execute(
            "UPDATE promo_codes SET uses_left=uses_left-1 WHERE id=$1", row["id"]
        )
        await conn.execute(
            "INSERT INTO promo_uses (promo_id, telegram_id) VALUES ($1,$2)",
            row["id"], telegram_id,
        )
        return {"ok": True, "discount": row["discount_pct"]}


@router.message(Command("promo"))
async def cmd_promo(message: Message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer(
            "🎟 <b>Промокод</b>\n\nИспользование: <code>/promo XXXXX</code>",
            parse_mode="HTML",
        )
        return

    code = parts[1].strip()
    result = await apply_promo(message.from_user.id, code)
    if result["ok"]:
        await message.answer(
            f"✅ <b>Промокод активирован!</b>\n\n"
            f"Скидка <b>{result['discount']}%</b> применена к вашему следующему заказу 🌿\n\n"
            f"<i>Скажите об этом дизайнеру при оформлении заказа.</i>",
            parse_mode="HTML",
        )
        # Сохраняем активный промокод в профиль пользователя
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE users SET updated_at=NOW() WHERE telegram_id=$1",
                message.from_user.id,
            )
    else:
        await message.answer(
            f"❌ <b>{result['reason']}</b>",
            parse_mode="HTML",
        )


@router.message(Command("newpromo"))
async def cmd_new_promo(message: Message):
    """Создаёт промокод. Только для дизайнера. Формат: /newpromo 20 10 [MYCODE]"""
    if message.from_user.id != DESIGNER_TELEGRAM_ID:
        return

    parts = message.text.split()
    if len(parts) < 3:
        await message.answer(
            "Формат: <code>/newpromo СКИДКА% ИСПОЛЬЗОВАНИЙ [КОД]</code>\n"
            "Пример: <code>/newpromo 20 10</code> или <code>/newpromo 15 1 FRIEND15</code>",
            parse_mode="HTML",
        )
        return

    try:
        discount = int(parts[1])
        uses     = int(parts[2])
        code     = parts[3].upper() if len(parts) > 3 else _gen_code()
    except ValueError:
        await message.answer("Неверный формат числа.")
        return

    pool = await get_pool()
    async with pool.acquire() as conn:
        try:
            await conn.execute(
                "INSERT INTO promo_codes (code, discount_pct, uses_left) VALUES ($1,$2,$3)",
                code, discount, uses,
            )
        except Exception:
            await message.answer(f"❌ Код <code>{code}</code> уже существует.", parse_mode="HTML")
            return

    await message.answer(
        f"✅ <b>Промокод создан!</b>\n\n"
        f"Код: <code>{code}</code>\n"
        f"Скидка: {discount}%\n"
        f"Использований: {uses}",
        parse_mode="HTML",
    )


@router.message(Command("promos"))
async def cmd_list_promos(message: Message):
    """Список всех промокодов — только для дизайнера."""
    if message.from_user.id != DESIGNER_TELEGRAM_ID:
        return
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT code, discount_pct, uses_left FROM promo_codes ORDER BY created_at DESC LIMIT 10"
        )
    if not rows:
        await message.answer("Промокодов нет. Создайте: /newpromo 20 5")
        return
    lines = [f"<code>{r['code']}</code> — {r['discount_pct']}% · осталось {r['uses_left']}" for r in rows]
    await message.answer(
        "🎟 <b>Активные промокоды:</b>\n\n" + "\n".join(lines),
        parse_mode="HTML",
    )
