"""SMS уведомления через smsc.ru — ВашСад Бот"""
import aiohttp
import logging
import os

log = logging.getLogger(__name__)

SMS_LOGIN    = os.getenv("SMS_LOGIN", "")
SMS_PASSWORD = os.getenv("SMS_PASSWORD", "")
SMS_PHONE    = os.getenv("SMS_PHONE", "")


async def send_sms(text: str) -> bool:
    """Отправить SMS на номер дизайнера."""
    if not SMS_LOGIN or not SMS_PASSWORD or not SMS_PHONE:
        log.warning("SMS не настроен — пропускаем")
        return False

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://smsc.ru/sys/send.php",
                params={
                    "login":   SMS_LOGIN,
                    "psw":     SMS_PASSWORD,
                    "phones":  SMS_PHONE,
                    "mes":     text,
                    "charset": "utf-8",
                    # fmt=1 убрали — берём текстовый ответ
                },
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                result = await resp.text()
                log.info(f"smsc.ru ответ: {result}")
                # Успех если нет слова ERROR
                if "ERROR" in result.upper():
                    log.error(f"SMS ошибка: {result}")
                    return False
                log.info(f"SMS отправлен на {SMS_PHONE}")
                return True

    except Exception as e:
        log.error(f"SMS exception: {e}")
        return False


async def notify_sms_new_order(service_name: str, phone: str, client_name: str) -> bool:
    text = f"ВашСад: заявка!\n{service_name}\n{client_name}\nТел: {phone}"
    return await send_sms(text)


async def notify_sms_new_project(area: str, phone: str, client_name: str) -> bool:
    text = f"ВашСад: проект!\nУчасток {area}\n{client_name}\nТел: {phone}"
    return await send_sms(text)


async def notify_sms_payment(service_name: str, amount: str) -> bool:
    text = f"ВашСад: оплата!\n{service_name}\nСумма: {amount} руб."
    return await send_sms(text)
