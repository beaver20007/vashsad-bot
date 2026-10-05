"""Конфигурация ВашСад Бот"""
import json
import logging
import os

from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger(__name__)


def _bool_env(name: str, default: bool = False) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


def _int_list_env(name: str) -> list[int]:
    """CSV переменная окружения -> список int, пустая строка -> []. Нечисловые элементы пропускаются
    (с предупреждением в журнал — опечатка в проде иначе тихо роняет получателя/id без следа)."""
    raw = os.getenv(name, "")
    out = []
    skipped = 0
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            out.append(int(part))
        except ValueError:
            skipped += 1
    if skipped:
        log.warning("_int_list_env(%s): пропущено %d нечисловых элементов", name, skipped)
    return out

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

# ── Запись на консультацию (handlers/booking.py) ─────────────────────
# Контакт для кнопки "Написать" на экране "нет слотов"/"запись скоро откроется".
# Пусто -> кнопка "Написать" не рисуется (не подставляем выдуманную ссылку).
BOOKING_CONTACT_URL = os.getenv("BOOKING_CONTACT_URL", "")

# Кто получает уведомление "Новая запись!" и экран "⚙️ Управление записью".
# Пусто -> по умолчанию оба DESIGNER_TELEGRAM_ID/_2 (как было до этого брифа).
BOOKING_RECIPIENT_IDS = _int_list_env("BOOKING_RECIPIENT_IDS")

# Пока запись не открыта клиентам — кнопка ведёт на экран-заглушку.
# Включается только сменой этой переменной (без правки кода).
BOOKING_OPEN_FOR_CLIENTS = _bool_env("BOOKING_OPEN_FOR_CLIENTS", False)

# Еженедельная автогенерация слотов (services/scheduler.py) — выключена по
# умолчанию, пока явно не включена.
BOOKING_AUTOSLOTS_ENABLED = _bool_env("BOOKING_AUTOSLOTS_ENABLED", False)

# Форматы консультаций: (название, ключ, цена ₽, длительность мин).
# Значения по умолчанию — подтверждены владельцем 03.10.2026, как в коде
# до этого брифа. Переопределяются через BOOKING_SERVICES_JSON (JSON-массив
# объектов {"label","key","price","duration_min"}) для будущих правок без
# деплоя кода; при ошибке разбора/отсутствии переменной — дефолт.
_BOOKING_SERVICES_DEFAULT = [
    {"label": "Онлайн-консультация 60 мин", "key": "consultation", "price": 2500, "duration_min": 60},
    {"label": "Разбор участка по фото",     "key": "photo_review", "price": 1500, "duration_min": 30},
    {"label": "Стратегия сада",             "key": "strategy",     "price": 3900, "duration_min": 90},
]


def _load_booking_services() -> list[dict]:
    raw = os.getenv("BOOKING_SERVICES_JSON", "")
    if not raw.strip():
        return _BOOKING_SERVICES_DEFAULT
    try:
        parsed = json.loads(raw)
        if not isinstance(parsed, list) or not parsed:
            raise ValueError("BOOKING_SERVICES_JSON должен быть непустым JSON-массивом")
        for item in parsed:
            if not all(k in item for k in ("label", "key", "price", "duration_min")):
                raise ValueError("каждый элемент BOOKING_SERVICES_JSON нуждается в label/key/price/duration_min")
        return parsed
    except (ValueError, TypeError) as e:
        import logging
        logging.getLogger(__name__).error(
            "config: BOOKING_SERVICES_JSON некорректен (%s) — использован дефолт", e
        )
        return _BOOKING_SERVICES_DEFAULT


BOOKING_SERVICES = _load_booking_services()

# Еженедельное расписание автогенерации слотов (дни недели пн=0..вс=6, часы,
# длительность мин). Переопределяется через BOOKING_AUTOSLOTS_DAYS /
# BOOKING_AUTOSLOTS_HOURS (CSV) при необходимости; дефолт = текущее ручное
# расписание (slots:add_week): будни, 10:00 и 14:00.
BOOKING_AUTOSLOTS_WEEKDAYS = [
    int(d) for d in os.getenv("BOOKING_AUTOSLOTS_WEEKDAYS", "0,1,2,3,4").split(",") if d.strip().isdigit()
] or [0, 1, 2, 3, 4]
BOOKING_AUTOSLOTS_HOURS = [
    int(h) for h in os.getenv("BOOKING_AUTOSLOTS_HOURS", "10,14").split(",") if h.strip().isdigit()
] or [10, 14]
BOOKING_AUTOSLOTS_DURATION_MIN = int(os.getenv("BOOKING_AUTOSLOTS_DURATION_MIN", "60"))
