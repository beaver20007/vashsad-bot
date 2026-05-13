"""Email уведомления — ВашСад Бот"""
import aiosmtplib
import logging
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

log = logging.getLogger(__name__)

EMAIL_LOGIN   = os.getenv("EMAIL_LOGIN", "")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD", "")
EMAIL_TO      = os.getenv("EMAIL_TO", EMAIL_LOGIN)  # куда слать, по умолчанию на себя


async def send_email(subject: str, body: str) -> bool:
    """Отправить email уведомление. Возвращает True если успешно."""
    if not EMAIL_LOGIN or not EMAIL_PASSWORD:
        log.warning("Email не настроен — пропускаем отправку")
        return False

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = EMAIL_LOGIN
        msg["To"]      = EMAIL_TO

        # HTML версия письма
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

        msg.attach(MIMEText(body, "plain", "utf-8"))
        msg.attach(MIMEText(html, "html", "utf-8"))

        await aiosmtplib.send(
            msg,
            hostname="smtp.gmail.com",
            port=587,
            start_tls=True,
            username=EMAIL_LOGIN,
            password=EMAIL_PASSWORD,
        )
        log.info(f"Email отправлен на {EMAIL_TO}")
        return True

    except Exception as e:
        log.error(f"Ошибка отправки email: {e}")
        return False


async def notify_email_new_order(user_info: str, service_name: str,
                                  price_str: str, phone: str, email: str, dt: str):
    """Уведомление о новой заявке на услугу."""
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
    """Уведомление о новом брифе на проект."""
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
