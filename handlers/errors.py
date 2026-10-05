"""Глобальный обработчик необработанных исключений (aiogram ErrorEvent).

Без него необработанное исключение в хендлере проглатывается aiogram:
ErrorsMiddleware (aiogram/dispatcher/middlewares/error.py) логирует update
как "not handled" и не отправляет пользователю ничего — тишина вместо
ответа (находка аудита error-handling-audit.md, 04.10.2026, пункт 3).

asyncio.CancelledError сюда никогда не попадёт и не должен перехватываться:
ErrorsMiddleware перехватывает `except Exception`, а CancelledError —
BaseException, не Exception, и проходит мимо этого обработчика как обычно.
"""
import logging

from aiogram.types import ErrorEvent

from services import i18n

log = logging.getLogger(__name__)


def _mask_user_id(event: ErrorEvent) -> str:
    update = event.update
    user = None
    if update.message and update.message.from_user:
        user = update.message.from_user
    elif update.callback_query and update.callback_query.from_user:
        user = update.callback_query.from_user
    elif update.inline_query and update.inline_query.from_user:
        user = update.inline_query.from_user
    if user is None:
        return "unknown"
    s = str(user.id)
    return f"***{s[-2:]}" if len(s) > 2 else f"***{s}"


async def global_error_handler(event: ErrorEvent) -> bool:
    """Логирует необработанное исключение и отвечает пользователю общим
    текстом ошибки. Не бросает исключений наружу — иначе стал бы сам вторым
    необработанным сбоем на том же update."""
    log.error(
        "Необработанное исключение %s в update %s (пользователь %s)",
        type(event.exception).__name__,
        event.update.event_type,
        _mask_user_id(event),
    )
    try:
        if event.update.callback_query:
            await event.update.callback_query.answer(i18n.t("error_generic"), show_alert=False)
        elif event.update.message:
            await event.update.message.answer(i18n.t("error_generic"))
    except Exception as e:
        log.warning("global_error_handler: не удалось ответить пользователю: %s", type(e).__name__)
    return True
