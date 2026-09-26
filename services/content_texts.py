"""Чтение текстов из общей таблицы content_strings.

Схема сверена 09.09.2026 с параллельным предложением vashsad-miniapp
(PR beaver20007/vashsad-miniapp#120): namespace+key составной ключ,
value — JSONB. Миграция (db/migrations_proposed/content_strings_up.sql)
ПОКА НЕ ПРИМЕНЕНА — см. README рядом с ней. Этот модуль сознательно
терпим к её отсутствию: пока таблицы/строки нет в реальной БД,
get_value() тихо возвращает default. Это позволяет смёржить и
задеплоить чтение уже сейчас — оно активируется само, без отдельного
релиза бота, в момент, когда миграцию накатят (со стороны miniapp,
db/migrate.py).
"""
import json
import logging

from services import bot_texts
from services.database import get_pool

log = logging.getLogger(__name__)

# Решение владельца 09.09.2026: понижение с "дипломированный ландшафтный
# дизайнер" (было в setup_bot.py/pdf_generator.py/export.py) до честной
# формулировки — единая для бота и miniapp (там же — lib/designerBio.ts).
DEFAULT_QUALIFICATION_LINE = "Garden Group, ТГУ — программы переподготовки «Ландшафтный дизайнер»"


async def get_value(namespace: str, key: str) -> dict | None:
    """Вернуть content_strings.value (распарсенный JSON) или None, если таблицы/строки нет."""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT value FROM content_strings WHERE namespace=$1 AND key=$2", namespace, key,
            )
    except Exception as e:
        log.warning("content_strings недоступна для (%r, %r): %s — используем значение по умолчанию", namespace, key, e)
        return None
    if not row:
        return None
    value = row["value"]
    return json.loads(value) if isinstance(value, str) else value


async def get_designer_qualification_line() -> str:
    """Строка квалификации дизайнера (сейчас: pdf_generator.py x2, plan.py, season_plan.py, guide.py, export.py)."""
    bio = await get_value("designer_bio", "default")
    if bio and bio.get("education"):
        return bio["education"]
    return DEFAULT_QUALIFICATION_LINE


# Статусы, тексты которых бот берёт из content_strings/order_status — тот же
# набор, что NOTIFY_STATUSES в miniapp (app/api/orders/[id]/status/route.ts).
# canceled сюда сознательно НЕ входит: по решению владельца (23.09.2026)
# на отмену клиенту ничего не шлётся ни из miniapp, ни из бота.
CONTENT_STATUSES = frozenset({"in_progress", "review", "done"})

SERVICE_PLACEHOLDER = "{service}"


def order_service_category(service_type: str | None) -> str:
    """service_type заявки -> категория слова для {service}.

    Зеркало orderServiceCategory() из vashsad-miniapp/lib/content.ts (правило
    живёт в коде miniapp, не в БД): custom_flowerbed/flowerbed -> flowerbed,
    container* -> container, всё остальное (id позиций прайса, legacy
    project и plan) -> project (решение владельца 23.09.2026).
    """
    s = (service_type or "").lower()
    if s in ("custom_flowerbed", "flowerbed"):
        return "flowerbed"
    if s.startswith("container"):
        return "container"
    return "project"


async def get_order_status_text(status: str, service_type: str | None) -> str | None:
    """Текст клиенту по статусу из content_strings/order_status, {service} уже подставлен.

    Слова берутся из service_words самой строки БД (общий источник с miniapp),
    в коде бота списка слов нет (запасное значение — content/bot_texts_defaults.json).
    None = «нет текста» (статус вне CONTENT_STATUSES, нет строки нигде, у
    шаблона нет слова для категории) — клиенту ничего не отправляется, и он
    никогда не увидит сырой плейсхолдер.
    """
    if status not in CONTENT_STATUSES:
        return None
    row = await get_value("order_status", status)
    if not row:
        row = bot_texts.default_row("order_status", status)
        if row:
            log.warning("order_status/%s нет в content_strings — используется файл-дефолт", status)
    if not row:
        return None
    template = row.get("notify_text")
    if not template:
        return None
    if SERVICE_PLACEHOLDER not in template:
        return template
    word = (row.get("service_words") or {}).get(order_service_category(service_type))
    if not word:
        log.warning("order_status/%s: нет слова service_words для %r — локальный текст", status, service_type)
        return None
    return template.replace(SERVICE_PLACEHOLDER, word)
