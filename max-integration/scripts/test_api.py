"""
Скрипт разведки MAX API.
Спринт 0: логирует реальные структуры ответов для сравнения с документацией.

Использование:
    python scripts/test_api.py
"""
import asyncio
import json
import os
import sys

from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent))

import httpx

MAX_API = "https://platform-api.max.ru"


async def test_api() -> None:
    token = os.environ.get("MAX_BOT_TOKEN_VASHSAD", "")
    if not token:
        print("❌ MAX_BOT_TOKEN_VASHSAD не задан")
        sys.exit(1)

    headers = {"Authorization": token, "Content-Type": "application/json"}

    async with httpx.AsyncClient(base_url=MAX_API, headers=headers) as client:

        print("=" * 60)
        print("GET /me — информация о боте")
        print("=" * 60)
        r = await client.get("/me")
        print(f"Status: {r.status_code}")
        print(json.dumps(r.json(), ensure_ascii=False, indent=2))

        print()
        print("=" * 60)
        print("POST /subscriptions — текущие подписки")
        print("=" * 60)
        r = await client.get("/subscriptions")
        print(f"Status: {r.status_code}")
        print(json.dumps(r.json(), ensure_ascii=False, indent=2))

        print()
        print("=" * 60)
        print("Long Polling — получение одного обновления (таймаут 5 сек)")
        print("Отправь сообщение боту прямо сейчас!")
        print("=" * 60)
        r = await client.get("/updates", params={"timeout": 5, "limit": 1}, timeout=10.0)
        print(f"Status: {r.status_code}")
        data = r.json()
        print(json.dumps(data, ensure_ascii=False, indent=2))

        if data.get("updates"):
            print()
            print("⚠️ Сравни структуру выше с документацией dev.max.ru/docs-api")
            print("Особое внимание: есть ли обёртка update_type/user_locale?")


if __name__ == "__main__":
    asyncio.run(test_api())
