"""Конфигурация ВашСад Бот"""
import os
from dotenv import load_dotenv

load_dotenv()

# ── Telegram ────────────────────────────────
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
DESIGNER_TELEGRAM_ID = int(os.getenv("DESIGNER_TELEGRAM_ID", "0"))

# ── Anthropic ───────────────────────────────
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = "claude-sonnet-4-5"
ANTHROPIC_MAX_TOKENS = 1500

# ── Лимиты Free-тира ────────────────────────
FREE_CHAT_LIMIT = int(os.getenv("FREE_CHAT_LIMIT", "10"))
FREE_PHOTO_LIMIT = int(os.getenv("FREE_PHOTO_LIMIT", "3"))
FREE_PLANTS_LIMIT = int(os.getenv("FREE_PLANTS_LIMIT", "3"))

# ── Подписка ────────────────────────────────
SUBSCRIPTION_PRICE = int(os.getenv("SUBSCRIPTION_PRICE", "299"))

# ── Дизайнер ────────────────────────────────
DESIGNER_NAME = os.getenv("DESIGNER_NAME", "Ваш дизайнер")
BOT_NAME = "ВашСад Бот"

# ── YooKassa ────────────────────────────────
YOOKASSA_SHOP_ID = os.getenv("YOOKASSA_SHOP_ID", "")
YOOKASSA_SECRET_KEY = os.getenv("YOOKASSA_SECRET_KEY", "")

# ── Прайс-лист ──────────────────────────────
SERVICES = {
    "consult": {
        "name": "Экспресс-консультация",
        "price": 1500,
        "duration": "24 часа",
        "description": "Разбор вашего участка + персональные рекомендации"
    },
    "plants_pro": {
        "name": "Подбор растений Pro",
        "price": 2500,
        "duration": "2 дня",
        "description": "Список 15–20 растений с фото, схемой посадки и уходом"
    },
    "analysis": {
        "name": "Анализ существующего сада",
        "price": 3900,
        "duration": "3 дня",
        "description": "Разбор фото вашего участка + план улучшений"
    },
    "seasonal": {
        "name": "Сезонный план ухода",
        "price": 3500,
        "duration": "2 дня",
        "description": "Персональный годовой календарь ухода за вашим садом в PDF"
    },
    "zoning": {
        "name": "Зонирование участка",
        "price": 4900,
        "duration": "3 дня",
        "description": "Схема зон, дорожек, въезда + описание каждой зоны"
    },
    "concept": {
        "name": "Концепция сада",
        "price": 9900,
        "duration": "5 дней",
        "description": "Стиль + мудборд + общая схема + список растений"
    },
    "project": {
        "name": "Индивидуальный проект",
        "price": 0,  # индивидуальный расчёт
        "duration": "по договору",
        "description": "Полный ландшафтный проект — индивидуальный расчёт"
    },
}
