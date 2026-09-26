"""Тексты бота из общей таблицы content_strings (namespace ``bot_text``).

Принцип «бот — тонкий слой поверх общей БД»: тексты живут в content_strings,
в коде их литералов нет. Значения из БД имеют приоритет. Файл
``content/bot_texts_defaults.json`` — запасной вариант на случай, если строки
ещё не засеяны или БД недоступна (бот не должен молчать). Каждая строка, взятая
из файла вместо БД, логируется на уровне WARNING.

Кэш в памяти: загружается при старте (``load()``), обновляется периодически
(``refresh_job`` в планировщике). Синхронные геттеры читают только кэш.
"""
import json
import logging
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

DEFAULTS_PATH = Path(__file__).resolve().parent.parent / "content" / "bot_texts_defaults.json"
NAMESPACE = "bot_text"

_defaults: dict[str, dict[str, Any]] | None = None
_db_rows: dict[str, dict[str, Any]] = {}
_warned: set[tuple[str, str]] = set()


def _load_defaults() -> dict[str, dict[str, Any]]:
    global _defaults
    if _defaults is None:
        _defaults = json.loads(DEFAULTS_PATH.read_text(encoding="utf-8"))
    return _defaults


async def load() -> None:
    """Перечитать строки namespace=bot_text из content_strings в кэш."""
    global _db_rows
    from services.database import get_pool  # локально: модуль без БД тоже импортируется
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT key, value FROM content_strings WHERE namespace=$1", NAMESPACE)
    except Exception as e:
        log.error("bot_texts: не удалось прочитать content_strings (%s) — остаются прежний кэш/файл-дефолт", e)
        return
    fresh: dict[str, dict[str, Any]] = {}
    for r in rows:
        v = r["value"]
        fresh[r["key"]] = json.loads(v) if isinstance(v, str) else v
    _db_rows = fresh
    log.info("bot_texts: загружено строк из content_strings: %d", len(fresh))


def get(key: str, namespace: str = NAMESPACE) -> Any:
    """Значение по ключу: БД (только namespace bot_text) -> файл-дефолт. KeyError, если нет нигде."""
    if namespace == NAMESPACE and key in _db_rows:
        return _db_rows[key]
    defaults = _load_defaults().get(namespace, {})
    if key not in defaults:
        raise KeyError(f"{namespace}/{key}")
    if (namespace, key) not in _warned:
        _warned.add((namespace, key))
        log.warning("bot_texts: %s/%s нет в content_strings — используется файл-дефолт", namespace, key)
    return defaults[key]


def default_row(namespace: str, key: str) -> dict[str, Any] | None:
    """Запасное значение строки другого namespace (например order_status) или None."""
    return _load_defaults().get(namespace, {}).get(key)


def all_keys() -> dict[str, dict[str, Any]]:
    """Все запасные значения — для скрипта засева."""
    return _load_defaults()


async def refresh_job() -> None:
    await load()
