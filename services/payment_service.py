"""
services/payment_service.py
Интеграция с YooKassa — создание платежей и проверка статуса.
Подход: ссылка + ручная проверка (без webhook, до деплоя).
"""
import logging
import uuid

from yookassa import Configuration, Payment

from config import YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY, YOOKASSA_RETURN_URL
from services.database import save_payment, get_payment_by_yookassa_id, mark_payment_succeeded, activate_subscription

log = logging.getLogger(__name__)


def _configure():
    Configuration.account_id = YOOKASSA_SHOP_ID
    Configuration.secret_key = YOOKASSA_SECRET_KEY


async def create_payment(
    telegram_id: int,
    amount: int,
    description: str,
    plan: str,
) -> tuple[str, str]:
    """Создаёт платёж в YooKassa. Возвращает (yookassa_id, payment_url)."""
    _configure()
    idempotency_key = str(uuid.uuid4())
    payment = Payment.create({
        "amount": {"value": str(amount), "currency": "RUB"},
        "confirmation": {
            "type": "redirect",
            "return_url": YOOKASSA_RETURN_URL,
        },
        "description": description,
        "metadata": {"telegram_id": str(telegram_id), "plan": plan},
        "capture": True,
    }, idempotency_key)

    payment_url = payment.confirmation.confirmation_url
    await save_payment(telegram_id, payment.id, amount, description, plan)
    log.info("Платёж создан: %s для пользователя %s", payment.id, telegram_id)
    return payment.id, payment_url


async def check_and_activate(telegram_id: int, yookassa_id: str) -> str:
    """
    Проверяет статус платежа в YooKassa.
    Если succeeded — активирует подписку и возвращает 'activated'.
    Иначе возвращает 'pending' | 'canceled' | 'unknown'.
    """
    _configure()
    try:
        payment = Payment.find_one(yookassa_id)
    except Exception as e:
        log.error("Ошибка проверки платежа %s: %s", yookassa_id, e)
        return "unknown"

    status = payment.status  # pending | waiting_for_capture | succeeded | canceled

    if status == "succeeded":
        row = await get_payment_by_yookassa_id(yookassa_id)
        if row and row["status"] != "succeeded":
            result = await mark_payment_succeeded(yookassa_id)
            if result:
                plan = result["plan"]
                months = 12 if plan == "year" else 1
                await activate_subscription(telegram_id, months)
                log.info("Подписка активирована для %s (%s мес.)", telegram_id, months)
        return "activated"

    return status  # 'pending' | 'canceled'
