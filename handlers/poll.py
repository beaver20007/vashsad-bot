"""Ежемесячный опрос: растение сезона."""
import logging
import os
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, PollAnswer
from services.scheduler import _scheduler_instance

router = Router()
log = logging.getLogger(__name__)

SEASON_PLANTS = {
    3: ["Крокус", "Пролеска", "Нарцисс", "Примула"],
    4: ["Тюльпан", "Нарцисс", "Мускари", "Гиацинт"],
    5: ["Сирень", "Яблоня", "Ирис", "Пион"],
    6: ["Роза", "Герань", "Лаванда", "Дельфиниум"],
    7: ["Лилия", "Эхинацея", "Рудбекия", "Астильба"],
    8: ["Флокс", "Гелениум", "Монарда", "Гортензия"],
    9: ["Астра", "Седум", "Вереск", "Хризантема"],
    10: ["Декоративная капуста", "Осенний крокус", "Хризантема", "Злаки"],
}

_poll_message_ids: dict[int, int] = {}  # chat_id -> message_id

async def send_monthly_poll(bot):
    from services.database import get_pool
    pool = await get_pool()
    month = __import__('datetime').datetime.now().month
    options = SEASON_PLANTS.get(month, SEASON_PLANTS[6])

    async with pool.acquire() as conn:
        users = await conn.fetch(
            "SELECT telegram_id FROM users WHERE is_banned IS NOT TRUE LIMIT 1000"
        )

    sent = 0
    for row in users:
        try:
            msg = await bot.send_poll(
                row['telegram_id'],
                question=f"🌿 Какое растение стало вашим открытием этого месяца?",
                options=options,
                is_anonymous=False,
                allows_multiple_answers=False,
            )
            sent += 1
            if sent >= 3:  # Limit for testing; remove in prod
                break
        except Exception:
            pass
    log.info(f"Monthly poll sent to {sent} users")

@router.message(Command("send_poll"))
async def cmd_send_poll(message: Message):
    designer_id = int(os.getenv("DESIGNER_TELEGRAM_ID", "0"))
    if message.from_user.id != designer_id:
        return
    await message.answer("📊 Запускаю опрос...")
    await send_monthly_poll(message.bot)
    await message.answer("✅ Опрос разослан!")

@router.message(Command("poll_results"))
async def cmd_poll_results(message: Message):
    designer_id = int(os.getenv("DESIGNER_TELEGRAM_ID", "0"))
    if message.from_user.id != designer_id:
        return
    try:
        from services.database import get_pool
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT option_id, COUNT(*) AS cnt
                FROM poll_answers
                GROUP BY option_id
                ORDER BY cnt DESC
                LIMIT 10
                """
            )
            total = await conn.fetchval("SELECT COUNT(*) FROM poll_answers")
        if not rows or not total:
            await message.answer("📊 Ответов на опросы пока нет.")
            return
        lines = ["📊 <b>Результаты опросов</b>\n"]
        for row in rows:
            pct = round(row['cnt'] / total * 100, 1)
            bar = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))
            lines.append(f"Вариант {row['option_id']}: {row['cnt']} голос(ов) — {pct}%\n{bar}")
        lines.append(f"\nВсего голосов: <b>{total}</b>")
        await message.answer("\n".join(lines), parse_mode="HTML")
    except Exception as e:
        log.exception("poll_results error")
        await message.answer(f"❌ Ошибка получения результатов: {e}")


@router.poll_answer()
async def handle_poll_answer(poll_answer: PollAnswer):
    # Just log for now; could store in DB for analytics
    log.info(f"Poll answer from {poll_answer.user.id}: options {poll_answer.option_ids}")
