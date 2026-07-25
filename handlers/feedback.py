"""Фаза 5: NPS-опрос после выполнения заявки"""
import logging
from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from config import DESIGNER_TELEGRAM_ID
from services.database import _pool

router = Router()
log = logging.getLogger(__name__)


class NpsCommentState(StatesGroup):
    waiting_comment = State()


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
        async with _pool.acquire() as conn:
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


# ── NPS 1-10 (batch survey from scheduler.send_nps_survey) ────────────────

@router.callback_query(F.data.startswith("nps_score:"))
async def cb_nps_score(callback: CallbackQuery, state: FSMContext):
    """Обрабатывает оценку 1-10 из еженедельного NPS-опроса."""
    score = int(callback.data.split(":")[1])
    telegram_id = callback.from_user.id

    # Сохраняем оценку в nps_responses
    try:
        async with _pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS nps_responses (
                    id SERIAL PRIMARY KEY,
                    telegram_id BIGINT NOT NULL,
                    order_id INTEGER,
                    score INTEGER NOT NULL CHECK (score BETWEEN 1 AND 10),
                    comment TEXT,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)
            await conn.execute(
                "INSERT INTO nps_responses (telegram_id, score) VALUES ($1, $2)",
                telegram_id, score,
            )
    except Exception as e:
        log.error("nps_score save error: %s", e)

    # Определяем категорию
    if score <= 6:
        category = "Критик"
    elif score <= 8:
        category = "Нейтральный"
    else:
        category = "Промоутер"

    # Уведомляем дизайнера о критиках
    if score <= 6 and DESIGNER_TELEGRAM_ID:
        try:
            await callback.bot.send_message(
                DESIGNER_TELEGRAM_ID,
                f"⚠️ <b>NPS-критик (оценка {score}/10)</b>\n"
                f"Пользователь: @{callback.from_user.username or telegram_id}",
                parse_mode="HTML",
            )
        except Exception:
            pass

    # Сохраняем score в FSM и задаём уточняющий вопрос
    await state.set_state(NpsCommentState.waiting_comment)
    await state.update_data(nps_telegram_id=telegram_id, nps_score=score)

    await callback.message.edit_text(
        f"{'⭐' * min(score, 5)} <b>Оценка {score}/10 — {category}!</b>\n\n"
        "Расскажите, что можно улучшить? (или напишите /skip, чтобы пропустить)",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(NpsCommentState.waiting_comment)
async def cb_nps_comment(message: Message, state: FSMContext):
    """Сохраняет текстовый комментарий к NPS-оценке."""
    data = await state.get_data()
    nps_telegram_id = data.get("nps_telegram_id")
    comment = None if message.text and message.text.strip().lower() in ("/skip", "skip") else message.text

    try:
        async with _pool.acquire() as conn:
            await conn.execute(
                """UPDATE nps_responses SET comment = $1
                   WHERE id = (
                       SELECT id FROM nps_responses
                       WHERE telegram_id = $2
                       ORDER BY created_at DESC LIMIT 1
                   )""",
                comment, nps_telegram_id or message.from_user.id,
            )
    except Exception as e:
        log.error("nps_comment save error: %s", e)

    await state.clear()
    await message.answer(
        "🌿 <b>Спасибо за отзыв!</b>\n\nВаше мнение помогает нам становиться лучше.",
        parse_mode="HTML",
    )


async def create_nps_table():
    """Создаёт таблицу NPS если не существует. Вызывается из init_db."""
    async with _pool.acquire() as conn:
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS nps_ratings (
            order_id    INTEGER PRIMARY KEY,
            telegram_id BIGINT,
            score       INTEGER CHECK(score BETWEEN 1 AND 5),
            created_at  TIMESTAMP DEFAULT NOW()
        )
        """)
