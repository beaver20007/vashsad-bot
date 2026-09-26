"""FSM-хранилище бота: свой префикс ключей, bot_id в ключе и TTL 24 часа (aiogram 3.7.0, общий Redis)."""
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.fsm.storage.base import DefaultKeyBuilder, StorageKey

import bot as bot_module


def _key() -> StorageKey:
    return StorageKey(bot_id=8681716628, chat_id=1288492012, user_id=1288492012)


def test_keys_differ_from_default_builder_and_carry_prefix():
    storage = bot_module.make_fsm_storage(MagicMock())
    default = DefaultKeyBuilder()  # то, что использовалось раньше и что используют другие боты
    for part in ("state", "data"):
        ours = storage.key_builder.build(_key(), part)
        theirs = default.build(_key(), part)
        assert ours != theirs
        assert ours.startswith(bot_module.FSM_KEY_PREFIX + ":")
        assert not theirs.startswith(bot_module.FSM_KEY_PREFIX)
        assert "8681716628" in ours  # id бота в ключе


def test_two_bots_same_user_get_different_keys():
    builder = bot_module.make_fsm_storage(MagicMock()).key_builder
    a = builder.build(StorageKey(bot_id=1, chat_id=5, user_id=5), "data")
    b = builder.build(StorageKey(bot_id=2, chat_id=5, user_id=5), "data")
    assert a != b


def test_state_ttl_is_24_hours_and_data_ttl_has_a_margin():
    storage = bot_module.make_fsm_storage(MagicMock())
    assert storage.state_ttl == 86400
    assert storage.data_ttl == 86400 + 3600 == 90000


def test_data_ttl_always_outlives_state_ttl():
    """state не должен пережить data: иначе data["slot_id"] и др. дадут KeyError у пользователя, сидящего в форме."""
    storage = bot_module.make_fsm_storage(MagicMock())
    assert storage.data_ttl > storage.state_ttl
    assert storage.data_ttl - storage.state_ttl == bot_module.FSM_DATA_TTL_MARGIN_SECONDS


@pytest.mark.asyncio
async def test_ttl_and_prefixed_key_reach_redis_calls():
    redis = MagicMock()
    redis.set = AsyncMock()
    storage = bot_module.make_fsm_storage(redis)

    await storage.set_state(_key(), "PlanForm:waiting_style")
    await storage.set_data(_key(), {"area": "6"})

    calls = redis.set.await_args_list
    assert len(calls) == 2
    by_part = {call.args[0].rsplit(":", 1)[-1]: call for call in calls}
    for call in calls:
        assert call.args[0].startswith(bot_module.FSM_KEY_PREFIX + ":")
    assert by_part["state"].kwargs["ex"] == 86400
    assert by_part["data"].kwargs["ex"] == 90000
