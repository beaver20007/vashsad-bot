"""Хендлер прайс-листа"""
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery

from config import SERVICES, SUBSCRIPTION_PRICE
from keyboards import price_keyboard, back_to_menu_keyboard

router = Router()

PRICE_TEXT = """💰 <b>Услуги ландшафтного дизайна</b>

🌱 <b>СТАРТОВЫЕ УСЛУГИ:</b>
• Экспресс-консультация — <b>1 500 ₽</b> (24 ч)
• Подбор растений Pro — <b>2 500 ₽</b> (2 дня)
• Анализ вашего сада — <b>3 900 ₽</b> (3 дня)
• Сезонный план ухода — <b>3 500 ₽</b> (2 дня)
• Зонирование участка — <b>4 900 ₽</b> (3 дня)
• Концепция сада — <b>9 900 ₽</b> (5 дней)

🏡 <b>ИНДИВИДУАЛЬНЫЙ ПРОЕКТ:</b>
Стоимость зависит от площади и состава:
• Эскизный проект — от <b>15 000 ₽</b>
• Дизайн-проект — от <b>35 000 ₽</b>
• Рабочий проект — от <b>60 000 ₽</b>
• Проект «под ключ» — от <b>120 000 ₽</b>

⭐ <b>ПОДПИСКА «САД ПРО»</b> — <b>299 ₽/мес</b>
Безлимитный AI + скидка 10% на все услуги"""


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


@router.callback_query(F.data == "menu:subscribe")
async def cb_subscribe(callback: CallbackQuery):
    from keyboards import subscribe_keyboard
    await callback.message.edit_text(
        f"⭐ <b>Подписка «Сад Про»</b>\n\n"
        f"Безлимитный доступ ко всем AI-функциям:\n"
        f"✅ Безлимитный AI-чат по садоводству\n"
        f"✅ Безлимитная фото-диагностика растений\n"
        f"✅ Безлимитный подбор растений\n"
        f"✅ Персональный календарь ухода\n"
        f"✅ История диалогов\n"
        f"✅ Скидка 10% на все услуги дизайнера\n\n"
        f"💳 <b>1 месяц — {SUBSCRIPTION_PRICE} ₽</b>\n"
        f"🎁 <b>12 месяцев — 2 490 ₽ (скидка 30%)</b>",
        parse_mode="HTML",
        reply_markup=subscribe_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("sub:"))
async def cb_sub_payment(callback: CallbackQuery):
    plan = callback.data.split(":")[1]
    if plan == "month":
        amount = SUBSCRIPTION_PRICE
        period = "1 месяц"
    else:
        amount = 2490
        period = "12 месяцев"

    await callback.message.edit_text(
        f"💳 <b>Оплата подписки</b>\n\n"
        f"Тариф: {period} — <b>{amount} ₽</b>\n\n"
        f"Для оплаты свяжитесь с нами:\n"
        f"Нажмите «Заказать проект» и укажите «Хочу оформить подписку»\n\n"
        f"<i>Скоро здесь будет автоматическая оплата через YooKassa!</i>",
        parse_mode="HTML",
        reply_markup=back_to_menu_keyboard(),
    )
    await callback.answer()
