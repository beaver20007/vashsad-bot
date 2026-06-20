"""
Одноразовый скрипт: настройка BotFather (имя, описание, about-текст, команды, фото профиля)
Запускать вручную после деплоя: python setup_bot.py
Для настройки webhook: python setup_bot.py --webhook
"""
import asyncio
import os
import sys
from dotenv import load_dotenv
import aiohttp

load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
BOT_NAME = os.getenv("BOT_NAME", "ВашСад — ландшафтный дизайн")
BOT_PHOTO_URL = os.getenv("BOT_PHOTO_URL", "")  # Прямая ссылка на фото профиля (JPEG/PNG)
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")  # Например: https://yourdomain.com

BASE_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

COMMANDS = [
    # --- Основные ---
    {"command": "start",       "description": "🌿 Главное меню"},
    {"command": "chat",        "description": "💬 AI-консультация с дизайнером"},
    {"command": "plants",      "description": "🌺 Подбор растений для вашего сада"},
    {"command": "photo",       "description": "📷 Диагностика растения по фото"},
    {"command": "plan",        "description": "🗺 Создать план участка"},
    {"command": "season_plan", "description": "📆 Сезонный план ухода за садом"},
    {"command": "guide",       "description": "📖 Гид по уходу за растениями (PDF)"},
    # --- Запись и консультации ---
    {"command": "book",        "description": "📅 Записаться на консультацию"},
    {"command": "slots",       "description": "🕐 Свободные слоты записи"},
    {"command": "watering",    "description": "💧 Напоминания о поливе"},
    {"command": "nurseries",   "description": "🏡 Питомники в вашем регионе"},
    # --- Заказы и оплата ---
    {"command": "order",       "description": "📋 Заказать услугу дизайнера"},
    {"command": "price",       "description": "💰 Прайс и подписка «Сад Про»"},
    {"command": "referral",    "description": "🎁 Реферальная программа"},
    {"command": "promo",       "description": "🏷 Применить промокод"},
    {"command": "callback",    "description": "📞 Запросить обратный звонок"},
    # --- Личный кабинет ---
    {"command": "profile",     "description": "👤 Профиль и лимиты"},
    {"command": "export",      "description": "📤 Экспорт данных"},
    {"command": "poll",        "description": "📊 Участвовать в опросе"},
]

# Команды только для дизайнера (не публикуются в публичный список):
# /stats, /broadcast, /broadcast_segment, /update_order, /export_clients,
# /send_poll, /poll_results, /ab_stats, /ban, /unban,
# /save_reply, /replies, /r, /delete_reply

DESCRIPTION = (
    "🌿 Бот дипломированного ландшафтного дизайнера. "
    "Природный стиль садов для Нижегородской и Владимирской областей.\n\n"
    "• AI-консультации по растениям и участку\n"
    "• Фото-диагностика болезней и вредителей\n"
    "• Подбор растений с учётом климата\n"
    "• Генерация плана участка\n"
    "• Заказ дизайн-проектов"
)

SHORT_DESCRIPTION = "ВашСад — AI-помощник ландшафтного дизайнера 🌿"


async def api_post(session: aiohttp.ClientSession, method: str, payload: dict) -> dict:
    url = f"{BASE_URL}/{method}"
    async with session.post(url, json=payload) as r:
        data = await r.json()
        ok = data.get("ok")
        desc = data.get("description", "")
        status = "OK" if ok else f"FAIL — {desc}"
        print(f"  {method}: {status}")
        return data


async def set_bot_photo(session: aiohttp.ClientSession, photo_url: str) -> None:
    """Скачать фото по URL и загрузить как фото профиля бота."""
    print(f"  Скачиваем фото: {photo_url}")
    async with session.get(photo_url) as r:
        if r.status != 200:
            print(f"  setBotProfilePhoto: SKIP — не удалось скачать фото (HTTP {r.status})")
            return
        photo_bytes = await r.read()

    form = aiohttp.FormData()
    form.add_field("photo", photo_bytes, filename="photo.jpg", content_type="image/jpeg")
    url = f"{BASE_URL}/setBotProfilePhoto"
    async with session.post(url, data=form) as r:
        data = await r.json()
        ok = data.get("ok")
        desc = data.get("description", "")
        status = "OK" if ok else f"FAIL — {desc}"
        print(f"  setBotProfilePhoto: {status}")


async def set_webhook() -> None:
    """Зарегистрировать Telegram webhook и вывести подтверждение."""
    if not BOT_TOKEN:
        print("TELEGRAM_BOT_TOKEN не задан в .env — выход.")
        return
    if not WEBHOOK_URL:
        print("WEBHOOK_URL не задан в .env — выход.")
        return

    webhook_endpoint = f"{WEBHOOK_URL}/telegram/{BOT_TOKEN}"
    allowed_updates = [
        "message",
        "callback_query",
        "inline_query",
        "poll_answer",
        "pre_checkout_query",
        "successful_payment",
    ]

    print("=== Настройка Telegram Webhook ===\n")

    async with aiohttp.ClientSession() as session:
        # Установить webhook
        payload = {
            "url": webhook_endpoint,
            "allowed_updates": allowed_updates,
        }
        await api_post(session, "setWebhook", payload)

        # Получить информацию о webhook
        async with session.get(f"{BASE_URL}/getWebhookInfo") as r:
            info = await r.json()

        if info.get("ok"):
            result = info["result"]
            print("\n📡 Webhook info:")
            print(f"  url:                    {result.get('url')}")
            print(f"  has_custom_certificate: {result.get('has_custom_certificate')}")
            print(f"  pending_update_count:   {result.get('pending_update_count', 0)}")
            print(f"  last_error_message:     {result.get('last_error_message', 'нет')}")
            print(f"  max_connections:        {result.get('max_connections', 40)}")
            print(f"  allowed_updates:        {result.get('allowed_updates', [])}")
        else:
            print(f"  getWebhookInfo: FAIL — {info.get('description', '')}")


async def main() -> None:
    if not BOT_TOKEN:
        print("TELEGRAM_BOT_TOKEN не задан в .env — выход.")
        return

    print("=== Настройка BotFather ===\n")

    async with aiohttp.ClientSession() as session:
        # Имя бота (отображаемое название)
        await api_post(session, "setMyName", {"name": BOT_NAME})

        # Полное описание (видно до /start)
        await api_post(session, "setMyDescription", {"description": DESCRIPTION})

        # Краткое описание (на странице бота)
        await api_post(session, "setMyShortDescription", {"short_description": SHORT_DESCRIPTION})

        # Список команд
        await api_post(session, "setMyCommands", {"commands": COMMANDS})

        # Фото профиля
        if BOT_PHOTO_URL:
            await set_bot_photo(session, BOT_PHOTO_URL)
        else:
            print("  setBotProfilePhoto: SKIP — BOT_PHOTO_URL не задан в .env")

    bot_username = os.getenv("BOT_USERNAME", "vashsad_bot")
    print(f"\n✅ BotFather настроен!")
    print(f"🤖 Бот: https://t.me/{bot_username}")


if __name__ == "__main__":
    if "--webhook" in sys.argv:
        asyncio.run(set_webhook())
    else:
        asyncio.run(main())
