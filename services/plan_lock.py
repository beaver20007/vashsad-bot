"""Распределённая блокировка plan:confirm (handlers/plan.py).

Контекст (docs/ORCHESTRATOR.md, "известные ограничения PR #48"):
старый мьютекс был `dict[int, asyncio.Lock]` в памяти процесса — защищал
только один процесс бота. Если бот когда-нибудь станет многопроцессным
(несколько polling-воркеров/вебхук-реплик), два тапа "Подтвердить" в разных
процессах снова прошли бы параллельно. Здесь — внешний lock через Redis
(SET NX EX), общий для всех процессов, видящих один REDIS_URL.

РЕШЕНИЕ: снятие блокировки — через WATCH/MULTI/EXEC (compare-and-delete),
а не через redis.asyncio.lock.Lock (библиотечный класс использует
EVAL/EVALSHA для атомарного release, что требует Lua на стороне Redis —
в тестовом окружении это fakeredis + пакет lupa, который на Windows CI
нетривиально собрать без компилятора Lua). WATCH/MULTI/EXEC даёт ту же
гарантию «снимает только владелец» (если значение ключа изменилось между
WATCH и EXEC — транзакция отменяется) без Lua и без новой тяжёлой
зависимости.
"""
import logging
import os
import uuid
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from redis.exceptions import RedisError

log = logging.getLogger(__name__)

# Короткий TTL (прежде всего — защита от "забытого" release при аварийном
# падении процесса внутри `async with`): длиннее типичного времени генерации
# плана (ask_claude + save_order), но не бесконечный.
PLAN_CONFIRM_LOCK_TTL = 45

_redis_client: aioredis.Redis | None = None


def _get_redis_client() -> aioredis.Redis | None:
    """None, если REDIS_URL не задан — вызывающий код трактует это как
    "Redis недоступен" и работает в режиме fail-open."""
    global _redis_client
    if _redis_client is None:
        url = os.getenv("REDIS_URL")
        if not url:
            return None
        _redis_client = aioredis.from_url(url, decode_responses=True)
    return _redis_client


class PlanConfirmLockBusy(Exception):
    """Блокировка уже занята другим владельцем — повторный тап во время
    обработки первого, а не состояние гонки (гонки не бывает: SET NX EX —
    одна атомарная команда)."""


@asynccontextmanager
async def plan_confirm_lock(telegram_id: int, redis_client: aioredis.Redis | None = None):
    """Захват: `SET key token NX EX ttl` — атомарно (единственная команда
    Redis, нет отдельных шагов "проверить" и "установить", поэтому нет окна
    для гонки). `token` — uuid4 этого вызова, снятие — только тем же токеном.

    Fail-open: если Redis недоступен (нет REDIS_URL или ошибка соединения),
    в лог уходит WARNING без текста исключения (в нём может быть адрес/
    пароль подключения) и код продолжает работу БЕЗ блокировки — как если
    бы захват удался. РЕШЕНИЕ: fail-open, потому что отказ Redis не должен
    останавливать генерацию плана для всех пользователей разом; альтернатива
    fail-closed ("Redis недоступен -> временно не принимаем подтверждения")
    — осознанно не выбрана, решение по ней — на Beaver.

    Поднимает PlanConfirmLockBusy, если ключ уже занят другим владельцем —
    вызывающий код должен мягко ответить пользователю, не повторяя действие.
    """
    key = f"plan_confirm_lock:{telegram_id}"
    token = uuid.uuid4().hex
    client = redis_client if redis_client is not None else _get_redis_client()

    if client is None:
        log.warning("plan_confirm_lock: REDIS_URL не задан — fail-open, блокировка не применяется")
        yield
        return

    try:
        acquired = await client.set(key, token, nx=True, ex=PLAN_CONFIRM_LOCK_TTL)
    except RedisError as e:
        log.warning("plan_confirm_lock: Redis недоступен при захвате (%s) — fail-open", type(e).__name__)
        yield
        return

    if not acquired:
        raise PlanConfirmLockBusy(key)

    try:
        yield
    finally:
        try:
            async with client.pipeline(transaction=True) as pipe:
                await pipe.watch(key)
                current = await pipe.get(key)
                if current == token:
                    pipe.multi()
                    pipe.delete(key)
                    await pipe.execute()
                else:
                    await pipe.reset()
        except RedisError as e:
            log.warning("plan_confirm_lock: не удалось снять блокировку (%s) — истечёт по TTL", type(e).__name__)
