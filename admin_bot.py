"""
🔐 ВашСад Админ-бот — отдельный процесс, доступ по таблице admin_users.

Второй Telegram-бот (свой токен из BotFather), long-polling, тот же Neon Postgres,
что и основной бот. Команды перенесены из handlers/admin.py и handlers/moderation.py
основного бота — см. docs/AGENTS.md, трек scaffold-admin-bot.
"""

import asyncio
import logging
import os
import ssl
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
import aiohttp

from handlers.admin_bot_handlers import router as admin_bot_router
from services.database import init_db, close_db
from services.admin_auth import create_admin_users_table, ensure_order_reply_column

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


def _make_session() -> AiohttpSession:
    # SSL (тот же Railway quirk, что в bot.py)
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE

    session = AiohttpSession()
    session._connector_type = aiohttp.TCPConnector
    session._connector_init = {"ssl": ssl_context}
    return session


async def main():
    await init_db()
    await create_admin_users_table()
    await ensure_order_reply_column()

    bot = Bot(
        token=os.getenv("ADMIN_BOT_TOKEN"),
        session=_make_session(),
    )

    # Второй Bot-инстанс на токене ОСНОВНОГО бота — только для отправки
    # сообщений клиентам (never polling). Клиенты никогда не писали
    # admin_bot'у (ADMIN_BOT_TOKEN) — Telegram не разрешит боту первым
    # написать пользователю, который с ним не переписывался. Все
    # клиент-адресованные сообщения (ответ на заявку, смена статуса,
    # /broadcast, /broadcast_segment) должны уходить через main_bot,
    # т.к. только с TELEGRAM_BOT_TOKEN у клиентов есть открытый чат
    # (см. трек admin-bot-layer-a-workflow).
    main_bot = Bot(
        token=os.getenv("TELEGRAM_BOT_TOKEN"),
        session=_make_session(),
    )

    dp = Dispatcher()
    dp.include_router(admin_bot_router)

    try:
        log.info("🔐 ВашСад Админ-бот запущен")
        await dp.start_polling(bot, main_bot=main_bot, skip_updates=True)
    finally:
        await bot.session.close()
        await main_bot.session.close()
        await close_db()


if __name__ == "__main__":
    asyncio.run(main())
