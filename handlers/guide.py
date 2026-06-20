"""Хендлер PDF-гайда — /guide"""
import io
import logging
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message, BufferedInputFile

from services.pdf_generator import generate_guide_pdf

router = Router()
log = logging.getLogger(__name__)


@router.message(Command("guide"))
async def cmd_guide(message: Message):
    await message.answer(
        "📄 <b>Генерирую гайд...</b>\n\n"
        "«15 растений для природного сада» — сейчас пришлю PDF!",
        parse_mode="HTML",
    )
    try:
        pdf_bytes = generate_guide_pdf()
        document = BufferedInputFile(pdf_bytes, filename="ВашСад_15_растений.pdf")
        await message.answer_document(
            document=document,
            caption=(
                "🌿 <b>15 растений для природного сада</b>\n\n"
                "Нижегородская и Владимирская области.\n"
                "Зимостойкие, неприхотливые, с минимумом ухода.\n\n"
                "Хотите индивидуальный подбор? Напишите /start 👇"
            ),
            parse_mode="HTML",
        )
    except Exception as e:
        log.error("Ошибка генерации PDF: %s", e)
        await message.answer(
            "⚠️ Не удалось создать PDF. Попробуйте чуть позже.",
        )
