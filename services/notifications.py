"""
services/notifications.py
Сервис рассылок и уведомлений пользователям через Telegram Bot API.
"""
import asyncio
import logging
import os
from typing import Callable, Coroutine, Any

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest, TelegramRetryAfter
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from services.database import get_all_user_ids, log_notification

log = logging.getLogger(__name__)

MINI_APP_URL = os.getenv("MINI_APP_URL", "https://vashsad-miniapp-pi.vercel.app")

# Сезонные советы (ключи: vesna / leto / osen / zima)
_SEASONAL_TIPS: dict[str, str] = {
    "vesna": (
        "🌱 <b>Весна в разгаре!</b>\n\n"
        "Самое время для посадки рассады, обрезки кустарников и первых подкормок. "
        "Не забудьте проверить почву на кислотность и при необходимости внести известь. "
        "Откройте ВашСад — там уже готов план работ на весну!"
    ),
    "leto": (
        "☀️ <b>Лето — горячая пора!</b>\n\n"
        "Поливайте растения утром или вечером, чтобы избежать ожогов. "
        "Следите за вредителями и не забывайте пасынковать томаты. "
        "В ВашСаде вы можете записать все наблюдения и получить совет от AI-агронома."
    ),
    "osen": (
        "🍂 <b>Осень — время подготовки!</b>\n\n"
        "Пора собирать урожай, мульчировать грядки и высаживать луковичные на весну. "
        "Укройте теплолюбивые растения до первых заморозков. "
        "Откройте ВашСад и составьте план осенних работ вместе с нами!"
    ),
    "zima": (
        "❄️ <b>Зима — время планирования!</b>\n\n"
        "Проверяйте укрытия и запасы семян, изучайте каталоги. "
        "Самое время спланировать сад мечты на будущий год. "
        "Воспользуйтесь ВашСадом — добавляйте растения в каталог и стройте планы!"
    ),
}


async def send_batch(
    bot: Bot,
    telegram_ids: list[int],
    text: str,
    rate: int = 25,
    parse_mode: str = "HTML",
) -> tuple[int, int]:
    """
    Отправляет сообщение списку пользователей порциями (rate сообщений/сек).

    :param bot: экземпляр Bot
    :param telegram_ids: список Telegram ID получателей
    :param text: текст сообщения
    :param rate: количество сообщений в секунду (размер чанка)
    :param parse_mode: режим разметки (по умолчанию HTML)
    :return: (sent_count, failed_count)
    """
    sent, failed = 0, 0
    for i in range(0, len(telegram_ids), rate):
        chunk = telegram_ids[i : i + rate]
        for uid in chunk:
            try:
                await bot.send_message(uid, text, parse_mode=parse_mode)
                sent += 1
            except (TelegramForbiddenError, TelegramBadRequest):
                failed += 1
            except Exception as exc:
                log.warning("send_batch: ошибка для %s: %s", uid, exc)
                failed += 1
        if i + rate < len(telegram_ids):
            await asyncio.sleep(1)
    log.info("send_batch: отправлено %d, ошибок %d (всего %d)", sent, failed, len(telegram_ids))
    return sent, failed


async def async_retry(
    coro_fn: Callable[[], Coroutine[Any, Any, Any]],
    retries: int = 3,
    delay: float = 1.0,
) -> Any:
    """
    Обёртка с повторными попытками для корутин, работающих с Telegram API.

    - При TelegramRetryAfter ждёт retry_after секунд и повторяет.
    - При сетевых ошибках (OSError, ConnectionError и т.п.) использует
      экспоненциальную задержку до retries попыток.
    - Прочие исключения пробрасываются немедленно.

    :param coro_fn: фабрика корутины (вызывается при каждой попытке)
    :param retries: максимальное количество повторов при сетевых ошибках
    :param delay: начальная задержка (секунд) для экспоненциального backoff
    :return: результат успешного вызова
    """
    _NETWORK_ERRORS = (OSError, ConnectionError, TimeoutError)
    attempt = 0
    while True:
        try:
            return await coro_fn()
        except TelegramRetryAfter as exc:
            wait = exc.retry_after + 0.5
            log.warning("async_retry: TelegramRetryAfter — ждём %.1f с", wait)
            await asyncio.sleep(wait)
            # Не считается за попытку с ошибкой — пробуем снова
        except _NETWORK_ERRORS as exc:
            attempt += 1
            if attempt > retries:
                log.error("async_retry: исчерпаны попытки (%d): %s", retries, exc)
                raise
            wait = delay * (2 ** (attempt - 1))
            log.warning("async_retry: сетевая ошибка (попытка %d/%d), ждём %.1f с: %s", attempt, retries, wait, exc)
            await asyncio.sleep(wait)


async def send_seasonal_tip(bot: Bot, season: str) -> int:
    """
    Рассылает сезонный совет всем пользователям.

    :param bot: экземпляр Bot
    :param season: один из ключей vesna / leto / osen / zima
    :return: количество успешно отправленных сообщений
    """
    text = _SEASONAL_TIPS.get(season)
    if not text:
        log.error("Неизвестный сезон для рассылки: %s", season)
        return 0

    user_ids = await get_all_user_ids()
    sent = 0

    for user_id in user_ids:
        try:
            await bot.send_message(user_id, text, parse_mode="HTML")
            await log_notification(user_id, f"seasonal_tip_{season}")
            sent += 1
        except TelegramForbiddenError:
            log.debug("Пользователь %s заблокировал бота — пропускаем", user_id)
        except Exception as exc:
            log.warning("Не удалось отправить сообщение пользователю %s: %s", user_id, exc)

    log.info("Сезонная рассылка (%s): отправлено %d / %d", season, sent, len(user_ids))
    return sent


async def send_task_reminder(bot: Bot, telegram_id: int, task_count: int) -> None:
    """
    Отправляет пользователю напоминание о задачах по уходу за садом.

    :param bot: экземпляр Bot
    :param telegram_id: Telegram ID пользователя
    :param task_count: количество задач на сегодня
    """
    text = (
        f"🌿 У вас {task_count} задач по уходу за садом на сегодня! "
        f"Откройте ВашСад."
    )
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🌿 Открыть ВашСад",
                    web_app=WebAppInfo(url=MINI_APP_URL),
                )
            ]
        ]
    )
    try:
        await bot.send_message(telegram_id, text, reply_markup=keyboard)
        await log_notification(telegram_id, "task_reminder")
    except TelegramForbiddenError:
        log.debug("Пользователь %s заблокировал бота — напоминание не отправлено", telegram_id)
    except Exception as exc:
        log.warning("Не удалось отправить напоминание пользователю %s: %s", telegram_id, exc)
