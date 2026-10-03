"""services/plan_lock.py — внешняя (Redis) блокировка plan:confirm, вариант Б
поверх старого in-process asyncio.Lock (docs/ORCHESTRATOR.md, "известные
ограничения PR #48": мьютекс в памяти процесса не видит параллельный тап,
попавший в другой процесс бота).

Подключения к боевому Redis ЗАПРЕЩЕНЫ — везде fakeredis или моки.
"""
import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import fakeredis.aioredis as fakeredis_aio
import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from handlers import plan
from services import plan_lock


def _fake_redis():
    return fakeredis_aio.FakeRedis(decode_responses=True)


# ── Захват/снятие — happy path ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_acquire_and_release_round_trip():
    r = _fake_redis()
    async with plan_lock.plan_confirm_lock(111, redis_client=r):
        val = await r.get("plan_confirm_lock:111")
        assert val is not None  # ключ выставлен на время владения
    assert await r.get("plan_confirm_lock:111") is None  # снят при выходе


@pytest.mark.asyncio
async def test_second_acquire_while_held_raises_busy_not_a_race():
    """SET NX EX — одна атомарная команда, поэтому это не гонка, а штатный
    отказ: второй вызов видит занятый ключ сразу же, без отдельного
    шага "проверить, потом записать"."""
    r = _fake_redis()
    async with plan_lock.plan_confirm_lock(222, redis_client=r):
        with pytest.raises(plan_lock.PlanConfirmLockBusy):
            async with plan_lock.plan_confirm_lock(222, redis_client=r):
                pytest.fail("не должно сюда дойти — лок уже занят")


@pytest.mark.asyncio
async def test_different_telegram_ids_do_not_block_each_other():
    r = _fake_redis()
    async with plan_lock.plan_confirm_lock(333, redis_client=r), plan_lock.plan_confirm_lock(444, redis_client=r):
        pass  # не бросает PlanConfirmLockBusy — разные ключи


@pytest.mark.asyncio
async def test_lock_reacquirable_after_release():
    r = _fake_redis()
    async with plan_lock.plan_confirm_lock(555, redis_client=r):
        pass
    async with plan_lock.plan_confirm_lock(555, redis_client=r):
        pass  # повторный захват после release — без исключения


@pytest.mark.asyncio
async def test_release_only_by_owner_token_does_not_touch_other_owner_key():
    """Снятие — compare-and-delete по токену (WATCH/MULTI/EXEC, без Lua —
    см. докстринг plan_lock.py). Если между захватом и снятием ключ успел
    достаться другому владельцу (например, истёк TTL и кто-то захватил
    заново) — снятие НЕ должно удалить чужую запись."""
    r = _fake_redis()
    key = "plan_confirm_lock:666"

    async with plan_lock.plan_confirm_lock(666, redis_client=r):
        # имитация: TTL истёк, другой процесс успел захватить лок заново
        await r.delete(key)
        await r.set(key, "someone-elses-token", nx=True, ex=plan_lock.PLAN_CONFIRM_LOCK_TTL)

    # после выхода из `async with` (снятие по СВОЕМУ токену, который уже не
    # совпадает с текущим значением ключа) чужая запись должна остаться цела
    assert await r.get(key) == "someone-elses-token"


# ── Fail-open: Redis недоступен ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_fail_open_when_redis_url_not_configured(caplog):
    """redis_client=None и _get_redis_client() тоже возвращает None (нет
    REDIS_URL) — код продолжает работу без блокировки, не бросает исключение."""
    with patch.object(plan_lock, "_get_redis_client", return_value=None), \
         caplog.at_level(logging.WARNING, logger="services.plan_lock"):
        async with plan_lock.plan_confirm_lock(777):
            pass  # не бросает исключение
    assert any("fail-open" in r.getMessage() for r in caplog.records)


@pytest.mark.asyncio
async def test_fail_open_on_redis_connection_error_does_not_leak_connection_string(caplog):
    """Redis недоступен (ConnectionError) при попытке SET — fail-open: код
    продолжает без блокировки, в лог уходит WARNING без текста исключения
    (там может быть адрес/пароль подключения)."""
    secret_in_exception = "redis://default:supersecretpassword@upstash.example:6379/0"
    broken_client = AsyncMock()
    broken_client.set = AsyncMock(side_effect=RedisConnectionError(secret_in_exception))

    with caplog.at_level(logging.WARNING, logger="services.plan_lock"):
        async with plan_lock.plan_confirm_lock(888, redis_client=broken_client):
            pass  # не бросает исключение — fail-open

    log_text = " ".join(r.getMessage() for r in caplog.records)
    assert "fail-open" in log_text
    assert "supersecretpassword" not in log_text
    assert secret_in_exception not in log_text


@pytest.mark.asyncio
async def test_fail_open_on_redis_error_during_release_does_not_raise():
    """Redis падает именно на этапе release (после успешного захвата) —
    код не должен бросить исключение наружу (ключ просто истечёт по TTL)."""
    client = AsyncMock()
    client.set = AsyncMock(return_value=True)
    client.pipeline = MagicMock(side_effect=RedisConnectionError("boom"))

    async with plan_lock.plan_confirm_lock(999, redis_client=client):
        pass  # release внутри finally не должен поднять исключение


# ── Константа TTL — зафиксирована, не magic-number на вызове ────────────────

def test_lock_ttl_is_a_short_named_constant():
    assert 30 <= plan_lock.PLAN_CONFIRM_LOCK_TTL <= 60


# ── Интеграция с handlers/plan.py: второй тап получает мягкий ответ ────────

def _make_callback(user_id: int = 42):
    callback = MagicMock()
    callback.from_user = MagicMock(id=user_id)
    callback.answer = AsyncMock()
    return callback


@pytest.mark.asyncio
async def test_plan_generate_second_tap_gets_busy_reply_not_duplicate_action():
    """Пока первый тап держит лок (имитация долгой _plan_generate), второй
    параллельный тап того же пользователя не должен повторно выполнить
    действие — только мягкий ответ callback.answer(...)."""
    r = _fake_redis()
    release_first = asyncio.Event()
    call_count = 0

    async def slow_plan_generate(callback, state):
        nonlocal call_count
        call_count += 1
        await release_first.wait()

    with patch.object(plan, "_plan_generate", slow_plan_generate), \
         patch.object(plan_lock, "_get_redis_client", return_value=r):
        cb1 = _make_callback(42)
        cb2 = _make_callback(42)
        state = MagicMock()

        task1 = asyncio.create_task(plan.plan_generate(cb1, state))
        await asyncio.sleep(0)  # дать первому таску захватить лок
        await plan.plan_generate(cb2, state)  # второй тап — должен получить отказ сразу

        release_first.set()
        await task1

    assert call_count == 1, "второй тап не должен повторно вызвать _plan_generate"
    cb2.answer.assert_awaited_once_with(plan.PLAN_CONFIRM_BUSY_TEXT, show_alert=False)
