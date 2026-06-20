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
from handlers.guide import router as guide_router
from handlers.referral import router as referral_router
from handlers.admin import router as admin_router
from handlers.payment import router as payment_router
from handlers.onboarding import router as onboarding_router
from handlers.feedback import router as feedback_router
from handlers.booking import router as booking_router
from handlers.promo import router as promo_router
from handlers.inline_mode import router as inline_router
from handlers.moderation import router as moderation_router, BanCheckMiddleware
from handlers.rate_limit import RateLimitMiddleware
from handlers.export import router as export_router
from handlers.payment_stars import router as payment_stars_router
from handlers.poll import router as poll_router
from handlers.watering import router as watering_router
from handlers.nurseries import router as nurseries_router
from handlers.season_plan import router as season_plan_router
from handlers.saved_replies import router as saved_replies_router
from handlers.channel import router as channel_router
from handlers.chat import router as chat_router   # ← chat ПОСЛЕДНИМ

from services.database import init_db, close_db
from services.scheduler import setup_scheduler
from services.webhook_server import start_webhook_server

import sentry_sdk

load_dotenv()

if os.getenv("SENTRY_DSN"):
    sentry_sdk.init(dsn=os.getenv("SENTRY_DSN"), traces_sample_rate=0.1)

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
    dp.message.middleware(BanCheckMiddleware())
    dp.callback_query.middleware(BanCheckMiddleware())
    dp.message.middleware(RateLimitMiddleware(limit=20, window=60))

    dp.include_routers(
        start_router,
        onboarding_router,
        plan_router,
        plants_router,
        order_router,
        photo_router,
        price_router,
        guide_router,
        referral_router,
        admin_router,
        payment_router,
        feedback_router,
        booking_router,
        promo_router,
        inline_router,
        moderation_router,
        export_router,
        payment_stars_router,
        poll_router,
        watering_router,
        nurseries_router,
        season_plan_router,
        saved_replies_router,
        channel_router,
        chat_router,    # ВСЕГДА ПОСЛЕДНИМ
    )

    # Сезонный планировщик рассылок
    scheduler = setup_scheduler(bot)
    scheduler.start()

    # NPS таблица
    from handlers.feedback import create_nps_table
    await create_nps_table()

    # Booking таблицы
    from handlers.booking import create_booking_tables
    await create_booking_tables()

    # Promo таблицы
    from handlers.promo import create_promo_table
    await create_promo_table()

    # Moderation колонки
    from handlers.moderation import create_moderation_tables
    await create_moderation_tables()

    # Webhook-сервер YooKassa (если настроен)
    webhook_runner = None
    if os.getenv("YOOKASSA_WEBHOOK_ENABLED", "").lower() in ("1", "true", "yes"):
        webhook_runner = await start_webhook_server(bot)

    try:
        log.info("🌿 ВашСад Бот запущен (PostgreSQL + Redis + Mini App + Scheduler)!")
        await dp.start_polling(bot, skip_updates=True)
    finally:
        scheduler.shutdown(wait=False)
        if webhook_runner:
            await webhook_runner.cleanup()
        await close_db()
        await redis.aclose()


if __name__ == "__main__":
    asyncio.run(main())
