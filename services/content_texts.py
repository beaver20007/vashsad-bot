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
        log.debug("content_strings недоступна для (%r, %r) (%s) — используем значение по умолчанию", namespace, key, e)
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
