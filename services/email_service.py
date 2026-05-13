"""Email уведомления через Resend API — ВашСад Бот"""
import aiohttp
import logging
import os

log = logging.getLogger(__name__)

RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
EMAIL_TO       = os.getenv("EMAIL_TO", "")
EMAIL_FROM     = "VashSad Bot <onboarding@resend.dev>"  # бесплатный домен Resend


async def send_email(subject: str, body: str) -> bool:
    """Отправить email через Resend HTTP API."""
    if not RESEND_API_KEY or not EMAIL_TO:
        log.warning("Email не настроен — пропускаем")
        return False

    html = f"""
    <html><body style="font-family: Arial, sans-serif; padding: 20px;">
    <div style="max-width: 600px; margin: 0 auto;">
        <div style="background: #2D6A4F; padding: 16px; border-radius: 8px 8px 0 0;">
            <h2 style="color: white; margin: 0;">🌿 ВашСад Бот</h2>
        </div>
        <div style="background: #f9f9f9; padding: 20px; border-radius: 0 0 8px 8px; white-space: pre-line;">
            {body}
        </div>
    </div>
    </body></html>
    """

    payload = {
        "from":    EMAIL_FROM,
        "to":      [EMAIL_TO],
        "subject": subject,
        "html":    html,
        "text":    body,
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.resend.com/emails",
                headers={
                    "Authorization": f"Bearer {RESEND_API_KEY}",
                    "Content-Type":  "application/json",
                },
                json=payload,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                data = await resp.json()
                if resp.status == 200 or resp.status == 201:
                    log.info(f"Email отправлен, id={data.get('id')}")
                    return True
                else:
                    log.error(f"Resend ошибка {resp.status}: {data}")
                    return False

    except Exception as e:
        log.error(f"Email exception: {e}")
        return False


async def notify_email_new_order(user_info: str, service_name: str,
                                  price_str: str, phone: str, email: str, dt: str):
    subject = f"🌿 Новая заявка — {service_name}"
    body = (
        f"НОВАЯ ЗАЯВКА — ВашСад Бот\n\n"
        f"Клиент: {user_info}\n"
        f"Услуга: {service_name}\n"
        f"Сумма: {price_str}\n"
        f"Телефон: {phone}\n"
        f"Email: {email}\n\n"
        f"Время: {dt}"
    )
    await send_email(subject, body)


async def notify_email_new_project(user_info: str, area: str, existing: str,
                                    style: str, wishes: str, phone: str,
                                    email: str, dt: str):
    subject = "🏡 Новый бриф на проект — ВашСад Бот"
    body = (
        f"НОВАЯ ЗАЯВКА НА ПРОЕКТ — ВашСад Бот\n\n"
        f"Клиент: {user_info}\n"
        f"Площадь: {area}\n"
        f"Участок: {existing}\n"
        f"Стиль: {style}\n"
        f"Пожелания: {wishes}\n"
        f"Телефон: {phone}\n"
        f"Email: {email}\n\n"
        f"Время: {dt}"
    )
    await send_email(subject, body)
