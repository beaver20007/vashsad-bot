"""
Фаза 2: YooKassa webhook-сервер (aiohttp).
Запускается рядом с polling-ботом на порту 8080.
Активирует подписку автоматически при событии payment.succeeded.
"""
import json
import logging
from aiohttp import web

log = logging.getLogger(__name__)

_bot_ref = None  # инжектируется из bot.py


def setup_webhook(bot):
    global _bot_ref
    _bot_ref = bot


async def yookassa_handler(request: web.Request) -> web.Response:
    # Verify Content-Type
    content_type = request.content_type or ""
    if "application/json" not in content_type:
        log.warning("YooKassa webhook: unexpected Content-Type: %s", content_type)

    try:
        data = await request.json()
    except Exception:
        return web.Response(status=400)

    event_type = data.get("event")
    obj = data.get("object", {})

    # Basic validation: object.type must be present
    if not obj.get("type") and not obj.get("id"):
        log.warning("YooKassa webhook: missing object fields, ignoring")
        return web.Response(status=400)

    log.info("YooKassa webhook: event=%s, id=%s", event_type, obj.get("id"))

    if event_type == "payment.succeeded":
        metadata = obj.get("metadata", {})
        telegram_id = metadata.get("telegram_id")
        plan = metadata.get("plan", "month")
        months = int(metadata.get("months", 12 if plan == "year" else 1))

        if telegram_id:
            try:
                from services.payment_service import activate_subscription
                await activate_subscription(int(telegram_id), months)
                log.info("Подписка активирована для %s (%s мес.)", telegram_id, months)

                if _bot_ref:
                    await _bot_ref.send_message(
                        int(telegram_id),
                        f"✅ <b>Подписка «Сад Про» активирована!</b>\n\n"
                        f"🌿 Срок: {months} мес.\n"
                        f"Теперь вам доступны безлимитный AI-чат и диагностика растений!",
                        parse_mode="HTML",
                    )
            except Exception as e:
                log.error("Webhook activate error: %s", e)
        else:
            log.warning("YooKassa webhook: payment.succeeded without telegram_id in metadata")

    return web.Response(status=200, text="ok")


def create_webhook_app() -> web.Application:
    app = web.Application()
    app.router.add_post("/webhook/yookassa", yookassa_handler)
    return app


async def start_webhook_server(bot, host="0.0.0.0", port=8080):
    setup_webhook(bot)
    app = create_webhook_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    log.info("✅ Webhook server запущен на %s:%s", host, port)
    return runner
