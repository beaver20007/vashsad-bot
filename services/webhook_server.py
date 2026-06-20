"""
Фаза 2: YooKassa webhook-сервер (aiohttp).
Запускается рядом с polling-ботом на порту 8080.
Активирует подписку автоматически при событии payment.succeeded.

Production hardening:
- IP whitelist (YooKassa CIDR ranges)
- SHA-1 HMAC signature verification
- Idempotency (processed payment IDs deduplication)
- Structured error handling with 500 on unexpected errors
"""
import hashlib
import hmac
import ipaddress
import json
import logging
from aiohttp import web

from config import YOOKASSA_SECRET_KEY

log = logging.getLogger(__name__)

_bot_ref = None  # инжектируется из bot.py

# YooKassa production IP ranges
_YOOKASSA_CIDRS = [
    ipaddress.ip_network("185.71.76.0/27"),
    ipaddress.ip_network("185.71.77.0/27"),
]

# Idempotency: set of already-processed payment IDs (in-memory; replace with Redis for multi-instance)
_processed_payment_ids: set[str] = set()


def setup_webhook(bot):
    global _bot_ref
    _bot_ref = bot


def _is_allowed_ip(remote: str | None) -> bool:
    """Return True if remote IP is from YooKassa or localhost."""
    if not remote:
        return False
    try:
        addr = ipaddress.ip_address(remote)
    except ValueError:
        return False
    if addr.is_loopback:
        return True
    return any(addr in cidr for cidr in _YOOKASSA_CIDRS)


def _verify_signature(body: bytes, header_sig: str | None) -> bool:
    """Verify SHA-1 HMAC signature from YooKassa.

    YooKassa computes: HMAC-SHA1(secret_key, raw_body)
    and sends the hex digest in HTTP_X_PAYMENT_SHA1 header.
    If no secret key is configured, skip verification (dev mode).
    """
    if not YOOKASSA_SECRET_KEY:
        log.warning("YOOKASSA_SECRET_KEY not set — skipping signature verification")
        return True
    if not header_sig:
        return False
    expected = hmac.new(
        YOOKASSA_SECRET_KEY.encode(),
        body,
        hashlib.sha1,
    ).hexdigest()
    return hmac.compare_digest(expected, header_sig.lower())


async def yookassa_handler(request: web.Request) -> web.Response:
    # ── 1. IP whitelist ──────────────────────────────────────────────────────
    remote_ip = request.remote  # aiohttp resolves X-Forwarded-For if trusted proxy
    if not _is_allowed_ip(remote_ip):
        log.warning("YooKassa webhook: forbidden IP %s", remote_ip)
        return web.Response(status=403, text="Forbidden")

    # ── 2. Read raw body (needed for signature check) ────────────────────────
    try:
        body = await request.read()
    except Exception as exc:
        log.error("YooKassa webhook: failed to read body: %s", exc)
        return web.Response(status=400)

    # ── 3. Signature verification ────────────────────────────────────────────
    sig_header = request.headers.get("HTTP_X_PAYMENT_SHA1") or request.headers.get("X-Payment-Sha1")
    if not _verify_signature(body, sig_header):
        log.warning("YooKassa webhook: invalid signature from %s", remote_ip)
        return web.Response(status=403, text="Invalid signature")

    # ── 4. Parse JSON ────────────────────────────────────────────────────────
    content_type = request.content_type or ""
    if "application/json" not in content_type:
        log.warning("YooKassa webhook: unexpected Content-Type: %s", content_type)

    try:
        data = json.loads(body)
    except Exception:
        log.warning("YooKassa webhook: invalid JSON body")
        return web.Response(status=400)

    event_type = data.get("event")
    obj = data.get("object", {})
    payment_id = obj.get("id")

    if not obj.get("type") and not payment_id:
        log.warning("YooKassa webhook: missing object fields, ignoring")
        return web.Response(status=400)

    log.info(
        "YooKassa webhook received: event=%s, payment_id=%s, ip=%s",
        event_type,
        payment_id,
        remote_ip,
    )

    # ── 5. Idempotency check ─────────────────────────────────────────────────
    if payment_id and payment_id in _processed_payment_ids:
        log.info("YooKassa webhook: payment %s already processed, skipping", payment_id)
        return web.Response(status=200, text="ok")

    # ── 6. Handle event ──────────────────────────────────────────────────────
    try:
        if event_type == "payment.succeeded":
            metadata = obj.get("metadata", {})
            telegram_id = metadata.get("telegram_id")
            plan = metadata.get("plan", "month")
            months = int(metadata.get("months", 12 if plan == "year" else 1))

            if telegram_id:
                from services.payment_service import activate_subscription
                await activate_subscription(int(telegram_id), months)
                log.info(
                    "Подписка активирована для telegram_id=%s (%s мес.), payment_id=%s",
                    telegram_id,
                    months,
                    payment_id,
                )

                if _bot_ref:
                    await _bot_ref.send_message(
                        int(telegram_id),
                        f"✅ <b>Подписка «Сад Про» активирована!</b>\n\n"
                        f"🌿 Срок: {months} мес.\n"
                        f"Теперь вам доступны безлимитный AI-чат и диагностика растений!",
                        parse_mode="HTML",
                    )
            else:
                log.warning(
                    "YooKassa webhook: payment.succeeded without telegram_id in metadata, payment_id=%s",
                    payment_id,
                )

        # Mark as processed only after successful handling
        if payment_id:
            _processed_payment_ids.add(payment_id)

    except Exception as exc:
        log.exception(
            "YooKassa webhook: unexpected error handling event=%s payment_id=%s: %s",
            event_type,
            payment_id,
            exc,
        )
        return web.Response(status=500, text="Internal Server Error")

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
    log.info("Webhook server запущен на %s:%s", host, port)
    return runner
