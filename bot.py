"""
🌿 ВашСад Бот — с PostgreSQL + Redis + Mini App
"""

import asyncio
import logging
import os
import ssl
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.fsm.storage.redis import RedisStorage
import aiohttp
import redis.asyncio as aioredis

from handlers.start import router as start_router
from handlers.plan import router as plan_router
from handlers.plants import router as plants_router
from handlers.order import router as order_router
from handlers.photo import router as photo_router
from handlers.price import router as price_router
from handlers.chat import router as chat_router   # ← chat ПОСЛЕДНИМ

from services.database import init_db, close_db

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


async def main():
    # ── База данных (Neon PostgreSQL) ──
    await init_db()

    # ── SSL (Railway quirk) ──
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

    # ── FSM Storage: Redis (Upstash) вместо Memory ──
    redis = aioredis.from_url(
        os.getenv("REDIS_URL"),
        encoding="utf-8",
        decode_responses=True,
    )
    storage = RedisStorage(redis=redis)

    dp = Dispatcher(storage=storage)

    # Порядок важен! FSM-роутеры ДО chat_router
    dp.include_routers(
        start_router,
        plan_router,
        plants_router,
        order_router,
        photo_router,
        price_router,
        chat_router,    # ВСЕГДА ПОСЛЕДНИМ
    )

    try:
        log.info("🌿 ВашСад Бот запущен (PostgreSQL + Redis + Mini App)!")
        await dp.start_polling(bot, skip_updates=True)
    finally:
        await close_db()
        await redis.aclose()


if __name__ == "__main__":
    asyncio.run(main())
