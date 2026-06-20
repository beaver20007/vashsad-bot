"""Хендлер прайс-листа и оплаты YooKassa"""
import logging
import os
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, LabeledPrice
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import SERVICES, SUBSCRIPTION_PRICE, YOOKASSA_SHOP_ID
from keyboards import price_keyboard, back_to_menu_keyboard

log = logging.getLogger(__name__)

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
async def cb_sub_payment(callback: CallbackQuery, bot: Bot):
    plan = callback.data.split(":")[1]
    if plan == "month":
        amount_kopecks = 29900  # 299 руб
        title = "Сад Про 1 месяц"
        period = "1 месяц"
        payload = "sub_month"
    else:
        amount_kopecks = 249000  # 2490 руб
        title = "Сад Про 12 месяцев"
        period = "12 месяцев"
        payload = "sub_year"

    provider_token = os.getenv("YOOKASSA_PROVIDER_TOKEN", "")

    await callback.answer()
    try:
        await bot.send_invoice(
            chat_id=callback.from_user.id,
            title=title,
            description=(
                f"Подписка «Сад Про» — {period}.\n"
                f"Безлимитный AI-чат, диагностика растений, скидка 10% на услуги дизайнера."
            ),
            payload=payload,
            provider_token=provider_token,  # пустая строка = Telegram Stars (XTR)
            currency="XTR" if not provider_token else "RUB",
            prices=[LabeledPrice(label=title, amount=amount_kopecks)],
        )
    except Exception as e:
        log.error("Ошибка отправки инвойса: %s", e)
        await callback.message.answer(
            "⚠️ Не удалось создать счёт. Попробуйте позже или напишите нам.",
            reply_markup=back_to_menu_keyboard(),
        )


@router.callback_query(F.data.startswith("pay_check:"))
async def cb_check_payment(callback: CallbackQuery):
    yookassa_id = callback.data.split(":", 1)[1]
    await callback.answer("Проверяем оплату...")
    try:
        from services.payment_service import check_and_activate
        status = await check_and_activate(callback.from_user.id, yookassa_id)
        if status == "activated":
            await callback.message.edit_text(
                "🎉 <b>Подписка активирована!</b>\n\n"
                "⭐ Добро пожаловать в «Сад Про»!\n"
                "Теперь у вас безлимитный AI-чат, диагностика и подбор растений.\n\n"
                "Скидка 10% на все услуги дизайнера активирована автоматически.",
                parse_mode="HTML",
                reply_markup=back_to_menu_keyboard(),
            )
        elif status == "pending":
            await callback.answer("⏳ Оплата ещё не поступила. Попробуйте через минуту.", show_alert=True)
        elif status == "canceled":
            await callback.answer("❌ Платёж отменён. Создайте новый.", show_alert=True)
        else:
            await callback.answer("⚠️ Статус неизвестен. Обратитесь к поддержке.", show_alert=True)
    except Exception as e:
        log.error("Ошибка проверки платежа: %s", e)
        await callback.answer("⚠️ Ошибка проверки. Попробуйте позже.", show_alert=True)
