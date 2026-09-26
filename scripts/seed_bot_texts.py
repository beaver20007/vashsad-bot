"""Засев content_strings (namespace bot_text) из content/bot_texts_defaults.json.

По умолчанию — dry-run: показывает, что будет вставлено/пропущено, БД не меняет.
  python scripts/seed_bot_texts.py                 # dry-run
  python scripts/seed_bot_texts.py --apply         # вставить недостающие строки (существующие не трогает)
  python scripts/seed_bot_texts.py --apply --overwrite   # перезаписать и существующие

Строки namespace order_status принадлежат miniapp и здесь не засеваются.
DATABASE_URL берётся из окружения (прямое соединение, не пулер, если есть DATABASE_URL_UNPOOLED).
"""
import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

import asyncpg

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from services.bot_texts import NAMESPACE, all_keys  # noqa: E402


async def main(apply: bool, overwrite: bool) -> None:
    dsn = os.getenv("DATABASE_URL_UNPOOLED") or os.getenv("DATABASE_URL")
    if not dsn:
        sys.exit("DATABASE_URL не задан")
    rows = all_keys()[NAMESPACE]
    conn = await asyncpg.connect(dsn)
    try:
        existing = {r["key"] for r in await conn.fetch("SELECT key FROM content_strings WHERE namespace=$1", NAMESPACE)}
        for key, value in rows.items():
            state = "есть в БД" if key in existing else "нет в БД"
            action = "пропуск"
            if key not in existing or overwrite:
                action = "ВСТАВКА/ОБНОВЛЕНИЕ" if apply else "будет вставлено/обновлено (dry-run)"
            print(f"{NAMESPACE}/{key}: {state} -> {action}")
            if apply and (key not in existing or overwrite):
                await conn.execute(
                    """INSERT INTO content_strings (namespace, key, value) VALUES ($1, $2, $3::jsonb)
                       ON CONFLICT (namespace, key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()""",
                    NAMESPACE, key, json.dumps(value, ensure_ascii=False),
                )
    finally:
        await conn.close()
    print("\nПрименено." if apply else "\nDry-run: БД не менялась.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--overwrite", action="store_true")
    args = ap.parse_args()
    asyncio.run(main(args.apply, args.overwrite))
