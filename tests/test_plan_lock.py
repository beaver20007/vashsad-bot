"""services/plan_lock.py — блокировка plan:confirm, два слоя: локальный
asyncio.Lock (защита в пределах процесса, работает всегда) + Redis SET NX EX
поверх него (защита между процессами, доработка 03.10.2026 по ревью Чата
ВашСад — см. докстринг модуля plan_lock.py).

Подключения к боевому Redis ЗАПРЕЩЕНЫ — везде fakeredis или моки.
"""
import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import fakeredis
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
    """Второй вызов с тем же telegram_id в том же процессе отбивается
    ЛОКАЛЬНЫМ слоем раньше, чем доходит до Redis (проверка+захват без await
    между ними — не гонка, не "проверить и записать")."""
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
async def test_redis_key_ttl_is_120_seconds():
    """TTL выставленного в Redis ключа соответствует PLAN_CONFIRM_LOCK_TTL
    (120 с — доработка 03.10.2026: запас под таймаут Claude 30 с + save_order
    + генерация PDF, прежние 45 с были слишком впритык)."""
    r = _fake_redis()
    key = "plan_confirm_lock:350"
    async with plan_lock.plan_confirm_lock(350, redis_client=r):
        ttl = await r.ttl(key)
        assert 100 < ttl <= 120, ttl


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


# ── Redis недоступен: локальный слой всё равно защищает процесс ────────────
# (доработка 03.10.2026 по ревью Чата ВашСад: раньше при недоступном Redis
# защиты от двойного тапа не было вообще — теперь локальный asyncio.Lock
# работает независимо от Redis.)

@pytest.mark.asyncio
async def test_no_redis_url_second_parallel_entry_same_process_still_busy():
    """REDIS_URL не задан (client=None) — локальный замок всё равно отбивает
    второй параллельный вход того же telegram_id в том же процессе."""
    with patch.object(plan_lock, "_get_redis_client", return_value=None):
        async with plan_lock.plan_confirm_lock(1001):
            with pytest.raises(plan_lock.PlanConfirmLockBusy):
                async with plan_lock.plan_confirm_lock(1001):
                    pytest.fail("не должно сюда дойти — локальный замок занят")


@pytest.mark.asyncio
async def test_redis_error_on_set_second_parallel_entry_same_process_still_busy():
    """Redis бросает RedisError на set (недоступен по сети) — локальный
    замок всё равно отбивает второй параллельный вход того же telegram_id."""
    broken_client = AsyncMock()
    broken_client.set = AsyncMock(side_effect=RedisConnectionError("boom"))

    async with plan_lock.plan_confirm_lock(1002, redis_client=broken_client):
        with pytest.raises(plan_lock.PlanConfirmLockBusy):
            async with plan_lock.plan_confirm_lock(1002, redis_client=broken_client):
                pytest.fail("не должно сюда дойти — локальный замок занят")


@pytest.mark.asyncio
async def test_no_redis_sequential_entries_both_succeed():
    """Без Redis последовательные (не параллельные) входы одного и того же
    telegram_id проходят оба — локальный замок освобождается между ними."""
    with patch.object(plan_lock, "_get_redis_client", return_value=None):
        async with plan_lock.plan_confirm_lock(1003):
            pass
        async with plan_lock.plan_confirm_lock(1003):
            pass  # без исключения


@pytest.mark.asyncio
async def test_exception_inside_block_releases_local_lock_even_without_redis():
    """Исключение внутри `async with` не должно оставлять локальный замок
    захваченным — следующий вход должен пройти."""
    with patch.object(plan_lock, "_get_redis_client", return_value=None):
        with pytest.raises(ValueError):
            async with plan_lock.plan_confirm_lock(1004):
                raise ValueError("бум")
        async with plan_lock.plan_confirm_lock(1004):
            pass  # замок освободился, несмотря на исключение в прошлый раз


# ── Два "процесса": локальные замки разные, Redis общий ────────────────────

@pytest.mark.asyncio
async def test_two_processes_simulation_redis_layer_catches_what_local_layer_cannot():
    """Два разных экземпляра клиента fakeredis, подключённые к ОДНОМУ
    серверу (имитация двух процессов бота с общим REDIS_URL). У процесса Б —
    СВОЙ пустой dict[int, asyncio.Lock] (в реальности это отдельный процесс
    со своей памятью; здесь эмулируем подменой plan_lock._local_locks на
    время вызова) — локальный слой его не остановит, но общий Redis должен."""
    server = fakeredis.FakeServer()
    client_process_a = fakeredis_aio.FakeRedis(server=server, decode_responses=True)
    client_process_b = fakeredis_aio.FakeRedis(server=server, decode_responses=True)

    async with plan_lock.plan_confirm_lock(2001, redis_client=client_process_a):
        with patch.object(plan_lock, "_local_locks", {}):
            # "Процесс Б" никогда не видел этот telegram_id — у него свой,
            # отдельный от процесса А, пустой локальный dict; единственное,
            # что может отбить вход, — общий Redis-ключ.
            with pytest.raises(plan_lock.PlanConfirmLockBusy):
                async with plan_lock.plan_confirm_lock(2001, redis_client=client_process_b):
                    pytest.fail("не должно сюда дойти — Redis-ключ занят процессом А")


# ── Отмена задачи (asyncio.CancelledError) в окне между захватом локального
#    замка и try/yield — доработка 03.10.2026 (ревью Чата ВашСад): раньше
#    этот участок был вне try/finally, отмена оставляла замок захваченным
#    навсегда. ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cancelled_during_redis_set_releases_local_lock_and_dict_entry():
    """CancelledError на `await client.set(...)` (единственная точка
    приостановки между acquire() локального замка и `try: yield`) не должна
    оставлять ни запись в _local_locks, ни захваченный замок."""
    broken_client = AsyncMock()
    broken_client.set = AsyncMock(side_effect=asyncio.CancelledError())

    with pytest.raises(asyncio.CancelledError):
        async with plan_lock.plan_confirm_lock(3001, redis_client=broken_client):
            pytest.fail("не должно сюда дойти — отмена на client.set")

    assert 3001 not in plan_lock._local_locks

    # Повторный вход (исправный клиент) должен пройти без Busy — подтверждает,
    # что локальный замок действительно освободился, а не просто "выглядит"
    # свободным по отсутствию записи в dict.
    ok_client = _fake_redis()
    async with plan_lock.plan_confirm_lock(3001, redis_client=ok_client):
        pass


@pytest.mark.asyncio
async def test_cancelled_inside_block_after_redis_key_acquired_cleans_up_both():
    """CancelledError внутри тела `async with`, когда Redis-ключ уже
    захвачен, — ключ должен быть удалён (внутренний finally) и локальный
    замок освобождён (внешний finally)."""
    r = _fake_redis()
    key = "plan_confirm_lock:3002"

    with pytest.raises(asyncio.CancelledError):
        async with plan_lock.plan_confirm_lock(3002, redis_client=r):
            assert await r.get(key) is not None  # ключ уже стоит
            raise asyncio.CancelledError()

    assert await r.get(key) is None  # Redis-ключ снят
    assert 3002 not in plan_lock._local_locks  # локальный замок освобождён


@pytest.mark.asyncio
async def test_real_task_cancel_during_lock_releases_everything():
    """Настоящая отмена задачи (asyncio.Task.cancel()), а не искусственно
    брошенный CancelledError, — замок и Redis-ключ свободны после завершения
    отменённой задачи."""
    r = _fake_redis()
    key = "plan_confirm_lock:3003"
    started = asyncio.Event()

    async def holder():
        async with plan_lock.plan_confirm_lock(3003, redis_client=r):
            started.set()
            await asyncio.sleep(10)

    task = asyncio.create_task(holder())
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert await r.get(key) is None
    assert 3003 not in plan_lock._local_locks


# ── Константа TTL — зафиксирована, не magic-number на вызове ────────────────

def test_lock_ttl_is_a_short_named_constant():
    """120 с (доработка 03.10.2026): дольше таймаута Claude 30 с
    (services/ai.py, ClientTimeout(total=30)) + save_order + генерация PDF —
    прежние 45 с были слишком впритык (см. docstring PLAN_CONFIRM_LOCK_TTL)."""
    assert plan_lock.PLAN_CONFIRM_LOCK_TTL == 120


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
