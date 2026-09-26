"""Хендлер прайс-листа"""
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from keyboards import price_keyboard

router = Router()

PRICE_TEXT = """💰 <b>Услуги ландшафтного дизайна</b>

🌱 <b>СТАРТОВЫЕ УСЛУГИ:</b>
Экспресс-консультация, подбор растений, анализ сада, сезонный план ухода,
зонирование участка, концепция сада.

🏡 <b>ИНДИВИДУАЛЬНЫЙ ПРОЕКТ:</b>
От эскиза до проекта «под ключ» — состав зависит от площади и задач.

Точный состав и стоимость обсуждаем индивидуально под ваш участок.
Оформите заявку в приложении ВашСад — там же можно выбрать стиль сада 🌿"""


@router.message(Command("price"))
async def cmd_price(message: Message):
    await message.answer(
        PRICE_TEXT,
        parse_mode="HTML",
        reply_markup=price_keyboard(),
    )


@router.callback_query(F.data == "menu:price")
async def cb_price(callback: CallbackQuery):
    await callback.message.edit_text(
        PRICE_TEXT,
        parse_mode="HTML",
        reply_markup=price_keyboard(),
    )
    await callback.answer()


