"""
handlers/season_plan.py
Команда /season_plan — годовой план ухода за садом на 12 месяцев.
Генерирует план через Claude API, сохраняет в БД, отправляет PDF.
"""
import logging
from datetime import date

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message, BufferedInputFile

from services.ai import ask_claude
from services.database import get_or_create_user, get_pool
from services.pdf_generator import generate_plan_pdf
from config import DESIGNER_NAME

log = logging.getLogger(__name__)

router = Router()

SEASON_PLAN_SYSTEM = """Ты — эксперт по природным садам средней полосы России.
Составляй подробные, практичные планы ухода за садом.
Отвечай структурированно, по-русски. Используй emoji для каждого месяца.
Давай конкретные сроки, названия растений, удобрений и процедур."""

DEFAULT_REGION = "Нижегородская область"


def _build_prompt(region: str) -> str:
    return (
        f"Ты эксперт по природным садам. Составь подробный план ухода за садом "
        f"на весь год (12 месяцев) для региона: {region}.\n\n"
        "Формат: каждый месяц отдельным разделом с emoji (например 🌱 Март, 🌸 Апрель и т.д.).\n"
        "Включи для каждого месяца:\n"
        "• Посев (что сеять, когда, как)\n"
        "• Посадка (деревья, кустарники, многолетники)\n"
        "• Обрезка (какие растения, как обрезать)\n"
        "• Подкормка (чем и когда удобрять)\n"
        "• Полив (режим и особенности)\n"
        "• Зимовка / подготовка к зиме (в осенне-зимние месяцы)\n\n"
        "Учитывай климат региона (морозные зимы, весенние заморозки, умеренное лето).\n"
        "Пиши подробно и практично. Минимум 50 слов на месяц."
    )


async def _save_season_plan(telegram_id: int, plan: str) -> None:
    """Сохранить сезонный план в профиль пользователя."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        # Добавляем колонку если ещё нет (безопасно для повторных вызовов)
        await conn.execute(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS season_plan TEXT"
        )
        await conn.execute(
            "UPDATE users SET season_plan = $1, updated_at = NOW() WHERE telegram_id = $2",
            plan, telegram_id,
        )


def _split_text(text: str, max_len: int = 4096) -> list[str]:
    """Разбить длинный текст на части не длиннее max_len символов."""
    if len(text) <= max_len:
        return [text]

    parts = []
    current = ""
    for line in text.splitlines(keepends=True):
        if len(current) + len(line) > max_len:
            if current:
                parts.append(current.rstrip())
            current = line
        else:
            current += line
    if current.strip():
        parts.append(current.rstrip())
    return parts


@router.message(Command("season_plan"))
async def cmd_season_plan(message: Message) -> None:
    """Генерация годового плана ухода за садом."""
    user = await get_or_create_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
    )

    region = user.region or DEFAULT_REGION

    # Уведомляем пользователя — генерация занимает время
    await message.answer(
        f"🌿 Готовлю годовой план ухода за садом для региона: <b>{region}</b>\n\n"
        "⏳ Это займёт около 30 секунд — Claude составляет детальный план на все 12 месяцев...",
        parse_mode="HTML",
    )

    # Вызов Claude API
    prompt = _build_prompt(region)
    plan_text = await ask_claude(
        messages=[{"role": "user", "content": prompt}],
        system=SEASON_PLAN_SYSTEM,
    )

    if plan_text.startswith("❌") or plan_text.startswith("⏳"):
        await message.answer(plan_text)
        return

    # Сохраняем план в профиль пользователя
    try:
        await _save_season_plan(message.from_user.id, plan_text)
    except Exception as e:
        log.warning(f"Не удалось сохранить season_plan для {message.from_user.id}: {e}")

    # Отправляем план текстом (разбиваем если > 4096 символов)
    header = f"📅 <b>Годовой план ухода за садом</b>\n📍 Регион: {region}\n\n"
    parts = _split_text(plan_text)

    for i, part in enumerate(parts):
        if i == 0:
            await message.answer(header + part, parse_mode="HTML")
        else:
            await message.answer(part)

    # Генерируем и отправляем PDF
    try:
        user_name = user.first_name or message.from_user.first_name or "Садовод"
        pdf_bytes = generate_plan_pdf(
            plan_text=plan_text,
            user_name=user_name,
            area="весь участок",
            style=f"Природный сад · {region}",
            designer_name=DESIGNER_NAME,
        )

        today = date.today().strftime("%Y-%m-%d")
        filename = f"season_plan_{today}.pdf"

        await message.answer_document(
            document=BufferedInputFile(pdf_bytes, filename=filename),
            caption=(
                f"📄 <b>Годовой план ухода за садом</b>\n"
                f"📍 {region} · {date.today().strftime('%d.%m.%Y')}\n\n"
                "Сохраните PDF для удобного использования в течение года!"
            ),
            parse_mode="HTML",
        )
    except Exception as e:
        log.error(f"Ошибка генерации PDF season_plan: {e}")
        await message.answer(
            "⚠️ PDF не удалось сформировать, но план выше сохранён в вашем профиле."
        )
