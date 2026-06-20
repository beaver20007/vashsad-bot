"""Хендлер Telegram Payments (YooKassa invoice)"""
import logging
from aiogram import Router
from aiogram.types import PreCheckoutQuery, Message
from aiogram.filters import Command

from services.database import activate_subscription

log = logging.getLogger(__name__)

router = Router()


@router.pre_checkout_query()
async def pre_checkout_handler(pre_checkout_query: PreCheckoutQuery):
    """Always approve pre-checkout queries."""
    await pre_checkout_query.answer(ok=True)


@router.message(lambda m: m.successful_payment is not None)
async def successful_payment_handler(message: Message):
    """Handle successful payment and activate subscription."""
    payment = message.successful_payment
    payload = payment.invoice_payload  # "sub_month" or "sub_year"
    user_id = message.from_user.id

    months = 12 if payload == "sub_year" else 1

    try:
        await activate_subscription(user_id, months=months)
        period = "12 месяцев" if months == 12 else "1 месяц"
        await message.answer(
            f"🎉 <b>Подписка «Сад Про» активирована!</b>\n\n"
            f"✅ Тариф: <b>{period}</b>\n"
            f"⭐ Добро пожаловать в «Сад Про»!\n\n"
            f"Теперь у вас:\n"
            f"• Безлимитный AI-чат по садоводству\n"
            f"• Безлимитная фото-диагностика растений\n"
            f"• Безлимитный подбор растений\n"
            f"• Скидка 10% на все услуги дизайнера",
            parse_mode="HTML",
        )
    except Exception as e:
        log.error("Ошибка активации подписки после оплаты: %s", e)
        await message.answer(
            "⚠️ Оплата прошла, но возникла ошибка активации. "
            "Пожалуйста, напишите нам — мы активируем вручную.",
        )
