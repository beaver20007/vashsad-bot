"""
Скрипт регистрации webhook для MAX бота.

Использование:
    python scripts/register_webhook.py https://your-domain.com/webhook/max

Запускать после каждого изменения URL деплоя.
"""
import asyncio
import os
import sys

from dotenv import load_dotenv

load_dotenv()

# Добавляем корень проекта в путь
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent))

from src.platforms.max_platform import MaxPlatform


async def main() -> None:
    if len(sys.argv) < 2:
        print("Использование: python scripts/register_webhook.py <WEBHOOK_URL>")
        print("Пример: python scripts/register_webhook.py https://my-app.vercel.app/webhook/max")
        sys.exit(1)

    webhook_url = sys.argv[1]
    token = os.environ.get("MAX_BOT_TOKEN_VASHSAD", "")

    if not token:
        print("❌ Переменная MAX_BOT_TOKEN_VASHSAD не задана в .env")
        sys.exit(1)

    platform = MaxPlatform(token=token)

    try:
        # Сначала проверяем бота
        me = await platform.get_me()
        print(f"✅ Бот: @{me.get('username')} (ID: {me.get('user_id')})")

        # Регистрируем webhook
        await platform.set_webhook(webhook_url)
        print(f"✅ Webhook зарегистрирован: {webhook_url}")

    except Exception as e:
        print(f"❌ Ошибка: {e}")
        raise
    finally:
        await platform.close()


if __name__ == "__main__":
    asyncio.run(main())
