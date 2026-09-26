"""Конфигурация ВашСад Бот"""
import os

from dotenv import load_dotenv

load_dotenv()

# ── Telegram ────────────────────────────────
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
DESIGNER_TELEGRAM_ID = int(os.getenv("DESIGNER_TELEGRAM_ID", "0"))
# Второй дизайнер — раньше уведомлялся только из handlers/plan.py (свой
# локальный os.getenv). Вынесено сюда, чтобы booking.py/feedback.py/
# services/scheduler.py могли уведомлять обоих тем же паттерном.
DESIGNER_TELEGRAM_ID_2 = int(os.getenv("DESIGNER_TELEGRAM_ID_2", "0"))

# ── Anthropic ───────────────────────────────
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = "claude-sonnet-4-5"
ANTHROPIC_MAX_TOKENS = 1500

# ── Лимиты Free-тира ────────────────────────
FREE_CHAT_LIMIT = int(os.getenv("FREE_CHAT_LIMIT", "10"))
FREE_PHOTO_LIMIT = int(os.getenv("FREE_PHOTO_LIMIT", "3"))
FREE_PLANTS_LIMIT = int(os.getenv("FREE_PLANTS_LIMIT", "3"))

# ── Дизайнер ────────────────────────────────
DESIGNER_NAME = os.getenv("DESIGNER_NAME", "Ваш дизайнер")
DESIGNER_NAME_GEN = os.getenv("DESIGNER_NAME_GEN", "Анны Аркадьевой")
BOT_NAME = "ВашСад Бот"

# ── Бот ─────────────────────────────────────
BOT_USERNAME = os.getenv("BOT_USERNAME", "washsad_ai_bot")

MINI_APP_URL = os.getenv("MINI_APP_URL", "https://vashsad-miniapp-pi.vercel.app")
WELCOME_IMAGE_URL = os.getenv("WELCOME_IMAGE_URL", "")

# ── Канал ────────────────────────────────────
CHANNEL_USERNAME = os.getenv("CHANNEL_USERNAME", "@vashsad_channel")

# ── Sentry ───────────────────────────────────
SENTRY_DSN = os.getenv("SENTRY_DSN", "")
