"""
Одноразовый скрипт: настройка BotFather (имя, описание, about-текст, команды, фото профиля)
Запускать вручную после деплоя: python setup_bot.py
"""
import asyncio
import os
from dotenv import load_dotenv
import aiohttp

load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
BOT_NAME = os.getenv("BOT_NAME", "ВашСад — ландшафтный дизайн")
BOT_PHOTO_URL = os.getenv("BOT_PHOTO_URL", "")  # Прямая ссылка на фото профиля (JPEG/PNG)

BASE_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

COMMANDS = [
    {"command": "start",    "description": "🌿 Главное меню"},
    {"command": "plants",   "description": "🌺 Подобрать растения"},
    {"command": "photo",    "description": "📷 Диагностика растения по фото"},
    {"command": "order",    "description": "📋 Заказать услугу дизайнера"},
    {"command": "booking",  "description": "📅 Записаться на консультацию"},
    {"command": "plan",     "description": "🗺 Сгенерировать план участка"},
    {"command": "guide",    "description": "📖 Гид по уходу за растениями"},
    {"command": "price",    "description": "💰 Прайс-лист и тарифы"},
    {"command": "profile",  "description": "👤 Профиль и лимиты"},
    {"command": "referral", "description": "🎁 Реферальная программа"},
    {"command": "promo",    "description": "🏷 Ввести промокод"},
    {"command": "export",   "description": "📤 Экспортировать данные"},
]

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
    asyncio.run(main())
