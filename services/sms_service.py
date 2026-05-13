"""SMS уведомления через smsc.ru — ВашСад Бот"""
import aiohttp
import logging
import os

log = logging.getLogger(__name__)

SMS_LOGIN    = os.getenv("SMS_LOGIN", "")
SMS_PASSWORD = os.getenv("SMS_PASSWORD", "")
SMS_PHONE    = os.getenv("SMS_PHONE", "")


async def send_sms(text: str) -> bool:
    """Отправить SMS на номер дизайнера. Возвращает True если успешно."""
    if not SMS_LOGIN or not SMS_PASSWORD or not SMS_PHONE:
        log.warning("SMS не настроен — пропускаем")
        return False

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://smsc.ru/sys/send.php",
                params={
                    "login":  SMS_LOGIN,
                    "psw":    SMS_PASSWORD,
                    "phones": SMS_PHONE,
                    "mes":    text,
                    "fmt":    1,   # ответ в JSON
                    "charset": "utf-8",
                },
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                data = await resp.json(content_type=None)
                if "error" in data:
                    log.error(f"SMS ошибка smsc.ru: {data}")
                    return False
                log.info(f"SMS отправлен на {SMS_PHONE}, id={data.get('id')}")
                return True

    except Exception as e:
        log.error(f"SMS exception: {e}")
        return False


async def notify_sms_new_order(service_name: str, phone: str, client_name: str) -> bool:
    """SMS о новой заявке на услугу."""
    text = (
        f"ВашСад: заявка!\n"
        f"{service_name}\n"
        f"{client_name}\n"
        f"Тел: {phone}"
    )
    return await send_sms(text)


async def notify_sms_new_project(area: str, phone: str, client_name: str) -> bool:
    """SMS о новом брифе на проект."""
    text = (
        f"ВашСад: проект!\n"
        f"Участок {area}\n"
        f"{client_name}\n"
        f"Тел: {phone}"
    )
    return await send_sms(text)


async def notify_sms_payment(service_name: str, amount: str) -> bool:
    """SMS о полученной оплате (вызывается из webhook YooKassa)."""
    text = (
        f"ВашСад: оплата!\n"
        f"{service_name}\n"
        f"Сумма: {amount} руб."
    )
    return await send_sms(text)
