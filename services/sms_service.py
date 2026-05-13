"""SMS уведомления через sms.ru — ВашСад Бот"""
import aiohttp
import logging
import os

log = logging.getLogger(__name__)

SMS_API_KEY = os.getenv("SMS_API_KEY", "")
SMS_PHONE   = os.getenv("SMS_PHONE", "")  # номер дизайнера для SMS


async def send_sms(text: str, phone: str = None) -> bool:
    """Отправить SMS. Возвращает True если успешно."""
    if not SMS_API_KEY or not SMS_PHONE:
        log.warning("SMS не настроен — пропускаем")
        return False

    to = phone or SMS_PHONE

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://sms.ru/sms/send",
                params={
                    "api_id": SMS_API_KEY,
                    "to":     to,
                    "msg":    text,
                    "json":   1,
                },
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                data = await resp.json()
                if data.get("status") == "OK":
                    log.info(f"SMS отправлен на {to}")
                    return True
                else:
                    log.error(f"SMS ошибка: {data}")
                    return False

    except Exception as e:
        log.error(f"SMS exception: {e}")
        return False


async def notify_sms_new_order(service_name: str, phone: str, client_name: str) -> bool:
    """SMS о новой заявке на услугу."""
    text = (
        f"ВашСад: новая заявка!\n"
        f"Услуга: {service_name}\n"
        f"Клиент: {client_name}\n"
        f"Тел: {phone}"
    )
    return await send_sms(text)


async def notify_sms_new_project(area: str, phone: str, client_name: str) -> bool:
    """SMS о новом брифе на проект."""
    text = (
        f"ВашСад: заявка на проект!\n"
        f"Участок: {area}\n"
        f"Клиент: {client_name}\n"
        f"Тел: {phone}"
    )
    return await send_sms(text)


async def notify_sms_payment(service_name: str, amount: str) -> bool:
    """SMS о полученной оплате (вызывается из webhook YooKassa)."""
    text = (
        f"ВашСад: оплата получена!\n"
        f"Услуга: {service_name}\n"
        f"Сумма: {amount} руб."
    )
    return await send_sms(text)
