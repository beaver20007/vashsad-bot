"""Чтение текстов из общей таблицы content_texts.

Миграция (db/migrations_proposed/content_texts_up.sql) ПОКА НЕ ПРИМЕНЕНА —
см. README рядом с ней. Этот модуль сознательно терпим к её отсутствию:
пока таблицы нет в реальной БД, get_text() тихо возвращает default. Это
позволяет смёржить и задеплоить чтение уже сейчас — оно активируется само,
без отдельного релиза бота, в момент, когда миграцию накатят на miniapp.
"""
import logging

from services.database import get_pool

log = logging.getLogger(__name__)

DEFAULT_QUALIFICATION_LINE = "Дипломированный ландшафтный дизайнер"


async def get_text(key: str, default: str) -> str:
    """Вернуть content_texts.body по ключу или default, если таблицы/строки нет."""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT body FROM content_texts WHERE key=$1", key)
    except Exception as e:
        log.debug("content_texts недоступна для ключа %r (%s) — используем значение по умолчанию", key, e)
        return default
    return row["body"] if row else default


async def get_designer_qualification_line() -> str:
    """Строка позиционирования дизайнера (сейчас: setup_bot.py, pdf_generator.py x2, export.py)."""
    return await get_text("designer.qualification_line", DEFAULT_QUALIFICATION_LINE)
