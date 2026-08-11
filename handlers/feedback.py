"""Фаза 5: NPS-опрос после выполнения заявки"""
import logging
from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton

from config import DESIGNER_TELEGRAM_ID
from services.database import get_pool

router = Router()
log = logging.getLogger(__name__)


async def send_nps_survey(bot: Bot, telegram_id: int, order_id: int):
    """Отправляет NPS-опрос пользователю. Вызывается из scheduler через 3 дня."""
    builder = InlineKeyboardBuilder()
    for score in range(1, 6):
        emoji = ["😞", "😕", "😐", "🙂", "😍"][score - 1]
        builder.button(text=f"{emoji} {score}", callback_data=f"nps:{order_id}:{score}")
    builder.adjust(5)

    try:
        await bot.send_message(
            telegram_id,
            "🌿 <b>Как прошла работа с дизайнером?</b>\n\n"
            "Оцените качество услуги от 1 до 5 — это займёт 5 секунд и очень поможет!",
            parse_mode="HTML",
            reply_markup=builder.as_markup(),
        )
    except Exception as e:
        log.warning("NPS send failed for %s: %s", telegram_id, e)


@router.callback_query(F.data.startswith("nps:"))
async def cb_nps(callback: CallbackQuery):
    _, order_id, score = callback.data.split(":")
    order_id = int(order_id)
    score    = int(score)

    try:
        async with get_pool().acquire() as conn:
            await conn.execute(
                """INSERT INTO nps_ratings (order_id, telegram_id, score)
                   VALUES ($1, $2, $3)
                   ON CONFLICT (order_id) DO UPDATE SET score=$3""",
                order_id, callback.from_user.id, score,
            )
    except Exception as e:
        log.error("NPS save error: %s", e)

    emoji = ["😞", "😕", "😐", "🙂", "😍"][score - 1]
    thanks = (
        "Спасибо! Рады, что всё понравилось 🌿" if score >= 4
        else "Спасибо за честность! Мы учтём это в следующий раз."
    )

    await callback.message.edit_text(
        f"{emoji} <b>Оценка {score}/5 сохранена!</b>\n\n{thanks}",
        parse_mode="HTML",
    )

    # Уведомляем дизайнера о низкой оценке
    if score <= 2 and DESIGNER_TELEGRAM_ID:
        try:
            await callback.bot.send_message(
                DESIGNER_TELEGRAM_ID,
                f"⚠️ <b>Низкая оценка NPS!</b>\n\n"
                f"Заявка #{order_id} — оценка {score}/5\n"
                f"Пользователь: @{callback.from_user.username or callback.from_user.id}",
                parse_mode="HTML",
            )
        except Exception:
            pass

    await callback.answer()


async def create_nps_table():
    """Создаёт таблицу NPS если не существует. Вызывается из init_db."""
    async with get_pool().acquire() as conn:
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS nps_ratings (
            order_id    INTEGER PRIMARY KEY,
            telegram_id BIGINT,
            score       INTEGER CHECK(score BETWEEN 1 AND 5),
            created_at  TIMESTAMP DEFAULT NOW()
        )
        """)
