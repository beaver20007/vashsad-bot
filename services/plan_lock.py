"""Блокировка plan:confirm (handlers/plan.py) — два слоя.

Контекст (docs/ORCHESTRATOR.md, "известные ограничения PR #48"):
старый мьютекс был `dict[int, asyncio.Lock]` в памяти процесса — защищал
только один процесс бота. Если бот когда-нибудь станет многопроцессным
(несколько polling-воркеров/вебхук-реплик), два тапа "Подтвердить" в разных
процессах снова прошли бы параллельно. Поверх него — внешний lock через
Redis (SET NX EX), общий для всех процессов, видящих один REDIS_URL.

Два слоя, оба обязательны:
1. **Локальный** `asyncio.Lock` на `telegram_id` (модульный `dict`) — проверка
   занятости и захват без `await` между ними (атомарно для однопоточного
   event loop, тот же приём, что был в handlers/plan.py до переезда на
   Redis). Работает ВСЕГДА, независимо от Redis — это и есть защита в
   пределах процесса при недоступном Redis (см. fail-open ниже).
2. **Redis** (`SET NX EX`) — поверх локального, для защиты между разными
   процессами бота. Берётся только если локальный слой захвачен успешно.

РЕШЕНИЕ (доработка 03.10.2026 по ревью Чата ВашСад, слово Beaver): если
Redis недоступен (нет `REDIS_URL` или `RedisError`) — WARNING в лог без
текста исключения (в нём может быть адрес/пароль подключения), и работа
продолжается ПОД ЛОКАЛЬНЫМ ЗАМКОМ (не "без блокировки совсем" — локальный
слой всегда активен). Это fail-open только на Redis-слое; защита от
двойного тапа в пределах одного процесса не теряется.

РЕШЕНИЕ: снятие Redis-блокировки — через WATCH/MULTI/EXEC (compare-and-delete),
а не через redis.asyncio.lock.Lock (библиотечный класс использует
EVAL/EVALSHA для атомарного release, что требует Lua на стороне Redis —
в тестовом окружении это fakeredis + пакет lupa, который на Windows CI
нетривиально собрать без компилятора Lua). WATCH/MULTI/EXEC даёт ту же
гарантию «снимает только владелец» (если значение ключа изменилось между
WATCH и EXEC — транзакция отменяется) без Lua и без новой тяжёлой
зависимости.
"""
import asyncio
import logging
import os
import uuid
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from redis.exceptions import RedisError

log = logging.getLogger(__name__)

# TTL Redis-ключа: длиннее таймаута вызова Claude 30 с (services/ai.py,
# ClientTimeout(total=30)) + save_order + генерация PDF — иначе при медленном
# ответе ключ истечёт до конца обработки, и второй тап пройдёт мимо
# Redis-слоя (локальный слой всё равно подстрахует в пределах процесса, но
# цель — не долетать до этого случая). Прежние 45 с были слишком впритык.
PLAN_CONFIRM_LOCK_TTL = 120

_redis_client: aioredis.Redis | None = None

# Локальный слой (защита в пределах процесса, не теряется при fail-open
# на Redis). Тот же модульный dict[int, asyncio.Lock], что был в
# handlers/plan.py до переезда на Redis — перенесён сюда, чтобы оба слоя
# жили в одном месте.
_local_locks: dict[int, asyncio.Lock] = {}


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
    """Два слоя (см. докстринг модуля).

    1. Локальный `asyncio.Lock` на `telegram_id` — проверка занятости и
       захват без `await` между ними, атомарно для однопоточного event loop.
       Занят — сразу `PlanConfirmLockBusy`, до Redis не доходим.
    2. Redis: `SET key token NX EX ttl` — атомарно (единственная команда,
       нет отдельных шагов "проверить" и "установить", окна для гонки нет).
       `token` — uuid4 этого вызова, снятие — только тем же токеном.
       Если Redis говорит "занято другим владельцем" — освобождаем локальный
       замок и поднимаем `PlanConfirmLockBusy` (гонки между процессами
       локальный слой не покрывает, это работа Redis-слоя).

    Fail-open — только на Redis-слое: если Redis недоступен (нет REDIS_URL
    или ошибка соединения), в лог уходит WARNING без текста исключения
    (в нём может быть адрес/пароль подключения), и обработка продолжается
    ПОД ЛОКАЛЬНЫМ ЗАМКОМ — защита от двойного тапа в пределах процесса не
    теряется. РЕШЕНИЕ: fail-closed на обоих слоях ("Redis недоступен ->
    временно не принимаем подтверждения вообще") осознанно не выбран —
    решение по нему остаётся на Beaver.

    Поднимает PlanConfirmLockBusy, если занято — вызывающий код должен
    мягко ответить пользователю, не повторяя действие.
    """
    local_lock = _local_locks.setdefault(telegram_id, asyncio.Lock())
    if local_lock.locked():
        raise PlanConfirmLockBusy(f"local:{telegram_id}")
    await local_lock.acquire()

    key = f"plan_confirm_lock:{telegram_id}"
    token = uuid.uuid4().hex
    client = redis_client if redis_client is not None else _get_redis_client()

    redis_acquired = False
    if client is None:
        log.warning(
            "plan_confirm_lock: REDIS_URL не задан — fail-open на Redis-слое, "
            "продолжаем под локальным замком",
        )
    else:
        try:
            redis_acquired = bool(await client.set(key, token, nx=True, ex=PLAN_CONFIRM_LOCK_TTL))
        except RedisError as e:
            log.warning(
                "plan_confirm_lock: Redis недоступен при захвате (%s) — fail-open на Redis-слое, "
                "продолжаем под локальным замком",
                type(e).__name__,
            )
        else:
            if not redis_acquired:
                _local_locks.pop(telegram_id, None)
                local_lock.release()
                raise PlanConfirmLockBusy(key)

    try:
        yield
    finally:
        if redis_acquired:
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
                log.warning(
                    "plan_confirm_lock: не удалось снять Redis-блокировку (%s) — истечёт по TTL",
                    type(e).__name__,
                )
        # pop + release локального замка — без await между ними (тот же
        # приём, что в старом handlers/plan.py): к моменту, когда другой
        # вызов сделает setdefault и увидит пустой dict, предыдущий владелец
        # уже гарантированно полностью освободил замок.
        _local_locks.pop(telegram_id, None)
        local_lock.release()
