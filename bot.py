"""
🌿 ВашСад Бот — MVP
Telegram-бот дипломированного ландшафтного дизайнера
"""

import asyncio
import logging
import os
import ssl
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.fsm.storage.memory import MemoryStorage
import aiohttp

# ВАЖНО: роутеры с FSM должны идти ДО chat_router
from handlers.start import router as start_router
from handlers.plan import router as plan_router
from handlers.plants import router as plants_router
from handlers.order import router as order_router
from handlers.photo import router as photo_router
from handlers.price import router as price_router
from handlers.chat import router as chat_router   # ← chat ПОСЛЕДНИМ

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


async def main():
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE

    session = AiohttpSession()
    session._connector_type = aiohttp.TCPConnector
    session._connector_init = {"ssl": ssl_context}

    bot = Bot(
        token=os.getenv("TELEGRAM_BOT_TOKEN"),
        session=session,
    )
    dp = Dispatcher(storage=MemoryStorage())

    # Порядок важен! FSM-роутеры ДО chat_router
    dp.include_routers(
        start_router,
        plan_router,    # план участка
        plants_router,  # подбор растений
        order_router,   # заказ / бриф
        photo_router,   # фото-диагностика
        price_router,   # прайс
        chat_router,    # AI-чат — ВСЕГДА ПОСЛЕДНИМ
    )

    log.info("🌿 ВашСад Бот запущен!")
    await dp.start_polling(bot, skip_updates=True)


if __name__ == "__main__":
    asyncio.run(main())
