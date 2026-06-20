"""Обработчик успешной оплаты Telegram Stars."""
import json
import logging

from aiogram import Router
from aiogram.types import Message, PreCheckoutQuery

router = Router()
log = logging.getLogger(__name__)


@router.pre_checkout_query()
async def handle_pre_checkout(pre_checkout: PreCheckoutQuery):
    # Must answer within 10 seconds
    await pre_checkout.answer(ok=True)


@router.message(lambda msg: msg.successful_payment is not None)
async def handle_successful_payment(message: Message):
    payment = message.successful_payment
    if payment.currency != "XTR":
        return  # Only handle Stars

    try:
        payload = json.loads(payment.invoice_payload)
    except Exception:
        payload = {}

    telegram_id = payload.get("telegram_id") or message.from_user.id
    months = int(payload.get("months", 1))
    plan = payload.get("plan", "month")

    log.info(f"Stars payment: user={telegram_id}, plan={plan}, months={months}, stars={payment.total_amount}")

    try:
        from services.payment_service import activate_subscription
        await activate_subscription(int(telegram_id), months)

        await message.answer(
            f"⭐ <b>Спасибо! Подписка «Сад Про» активирована!</b>\n\n"
            f"✅ Оплачено: {payment.total_amount} Stars\n"
            f"🌿 Срок: {months} {'месяц' if months == 1 else 'месяца' if months < 5 else 'месяцев'}\n\n"
            f"Теперь вам доступны:\n"
            f"• Безлимитный AI-чат 💬\n"
            f"• Диагностика растений 📸\n"
            f"• Скидка 10% на услуги дизайнера 🌿",
            parse_mode="HTML"
        )
    except Exception as e:
        log.error(f"Failed to activate Stars subscription: {e}")
        await message.answer("✅ Оплата получена! Подписка будет активирована в течение минуты.")
