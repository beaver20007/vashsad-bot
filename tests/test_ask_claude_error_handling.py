"""Сбой/таймаут ask_claude (❌/⏳/⚠️, services/ai.py) не должен тратить лимит клиента,
создавать мусорную запись или показывать текст внутренней ошибки как результат —
тот же принцип, что уже применён в handlers/plan.py (PR #48), распространён на
handlers/season_plan.py, chat.py, photo.py, plants.py.

Ниже также — тесты самого ask_claude на сетевом уровне (services/ai.py), трек
fix/ai-timeout-except (04.10.2026): до фикса `except aiohttp.ClientTimeout` —
класс НАСТРОЕК, не исключение, при любом исключении внутри try Python падал
TypeError-ом на этапе сверки с этим except, не доходя даже до `except Exception`.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

from services import ai as ai_module
from services.ai import ERROR_PREFIXES, ask_claude

ERROR_TEXTS = [
    "❌ Ошибка AI. Попробуйте позже или нажмите «Заказать проект» для связи с дизайнером.",
    "⏳ Запрос занял слишком много времени. Попробуйте ещё раз.",
    "⚠️ AI-консультация временно недоступна.\n\n"
    "Для получения совета напишите напрямую дизайнеру — нажмите кнопку «Заказать проект».",
]


def test_error_texts_cover_all_prefixes():
    assert all(any(t.startswith(p) for t in ERROR_TEXTS) for p in ERROR_PREFIXES)


# ── services/ai.py: ask_claude — перехват исключений сетевого уровня ───────
# (fix/ai-timeout-except, 04.10.2026)

def _session_cm(post_side_effect=None, status=200, resp_text="", resp_json=None):
    """Мок для `async with aiohttp.ClientSession() as session, session.post(...) as resp:`.
    post_side_effect — исключение, которое бросает вход в контекст POST (сетевая
    ошибка/таймаут); без него — подставляется resp с заданным статусом/телом."""
    post_cm = MagicMock()
    if post_side_effect is not None:
        post_cm.__aenter__ = AsyncMock(side_effect=post_side_effect)
    else:
        resp = MagicMock()
        resp.status = status
        resp.text = AsyncMock(return_value=resp_text)
        resp.json = AsyncMock(return_value=resp_json or {"content": [{"text": "ok"}]})
        post_cm.__aenter__ = AsyncMock(return_value=resp)
    post_cm.__aexit__ = AsyncMock(return_value=False)

    session = MagicMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    session.post = MagicMock(return_value=post_cm)
    return session


@pytest.mark.asyncio
async def test_ask_claude_timeout_returns_the_waiting_message():
    """Настоящий таймаут (TimeoutError, он же asyncio.TimeoutError с Python
    3.11; его подкласс — aiohttp.ServerTimeoutError) должен давать "⏳ ...",
    а не падать TypeError на этапе сверки с except aiohttp.ClientTimeout
    (поведение до фикса)."""
    session = _session_cm(post_side_effect=TimeoutError())
    with patch.object(ai_module, "ANTHROPIC_API_KEY", "test-key"), \
         patch.object(ai_module.aiohttp, "ClientSession", return_value=session):
        result = await ask_claude([{"role": "user", "content": "привет"}])
    assert result == "⏳ Запрос занял слишком много времени. Попробуйте ещё раз."


@pytest.mark.asyncio
async def test_ask_claude_other_network_error_returns_generic_error_message():
    """aiohttp.ClientError (не таймаут) — другая ветка, общий "❌ Произошла ошибка..."."""
    session = _session_cm(post_side_effect=aiohttp.ClientConnectionError("boom"))
    with patch.object(ai_module, "ANTHROPIC_API_KEY", "test-key"), \
         patch.object(ai_module.aiohttp, "ClientSession", return_value=session):
        result = await ask_claude([{"role": "user", "content": "привет"}])
    assert result == "❌ Произошла ошибка. Попробуйте позже."


@pytest.mark.asyncio
async def test_ask_claude_non_200_status_returns_ai_error_message():
    """Статус не 200 — отдельная ветка без исключения вообще; должна по-прежнему
    (независимо от фикса except) возвращать "Ошибка AI"."""
    session = _session_cm(status=500, resp_text="internal error")
    with patch.object(ai_module, "ANTHROPIC_API_KEY", "test-key"), \
         patch.object(ai_module.aiohttp, "ClientSession", return_value=session):
        result = await ask_claude([{"role": "user", "content": "привет"}])
    assert result == "❌ Ошибка AI. Попробуйте позже или нажмите «Заказать проект» для связи с дизайнером."


# ── season_plan.py ────────────────────────────────────────────────────────

def _make_season_message(user_id: int = 1288492012) -> MagicMock:
    msg = MagicMock()
    msg.from_user = SimpleNamespace(id=user_id, username="u", first_name="P")
    msg.answer = AsyncMock()
    return msg


@pytest.mark.asyncio
@pytest.mark.parametrize("error_text", ERROR_TEXTS)
async def test_season_plan_error_is_not_saved_or_sent_as_plan(error_text):
    from handlers import season_plan

    user = SimpleNamespace(region="Нижегородская область")
    message = _make_season_message()

    with patch.object(season_plan, "get_or_create_user", AsyncMock(return_value=user)), \
         patch.object(season_plan, "ask_claude", AsyncMock(return_value=error_text)), \
         patch.object(season_plan, "_save_season_plan", AsyncMock()) as save_plan:
        await season_plan.cmd_season_plan(message)

    save_plan.assert_not_awaited()
    # Первый answer — «Готовлю план...», второй (последний) — текст ошибки, не план
    assert message.answer.await_count == 2
    last_text = message.answer.await_args.args[0]
    assert last_text == error_text


@pytest.mark.asyncio
async def test_season_plan_success_is_saved(monkeypatch):
    from handlers import season_plan

    user = SimpleNamespace(region="Нижегородская область")
    message = _make_season_message()

    with patch.object(season_plan, "get_or_create_user", AsyncMock(return_value=user)), \
         patch.object(season_plan, "ask_claude", AsyncMock(return_value="🌱 Март: ...")), \
         patch.object(season_plan, "_save_season_plan", AsyncMock()) as save_plan, \
         patch.object(season_plan, "generate_plan_pdf", MagicMock(return_value=b"%PDF")), \
         patch.object(season_plan, "get_designer_qualification_line", AsyncMock(return_value="q")):
        await season_plan.cmd_season_plan(message)

    save_plan.assert_awaited_once()


# ── chat.py ──────────────────────────────────────────────────────────────

def _make_chat_message(text="Что посадить в тени?", user_id=1288492012) -> MagicMock:
    msg = MagicMock()
    msg.text = text
    msg.chat = MagicMock(id=user_id)
    msg.from_user = SimpleNamespace(id=user_id, username="u", first_name="P")
    msg.answer = AsyncMock()
    msg.bot = MagicMock()
    msg.bot.send_chat_action = AsyncMock()
    return msg


def _chat_user(**kw):
    base = dict(telegram_id=1288492012, region=None, bonus_messages=0, chat_count=0, chat_history=[])
    base.update(kw)
    return SimpleNamespace(**base)


@pytest.mark.asyncio
@pytest.mark.parametrize("error_text", ERROR_TEXTS)
async def test_chat_error_does_not_spend_limit_or_history(error_text):
    from handlers import chat

    user = _chat_user()
    message = _make_chat_message()

    with patch.object(chat, "get_or_create_user", AsyncMock(return_value=user)), \
         patch.object(chat, "can_use_chat", return_value=True), \
         patch.object(chat, "ask_claude", AsyncMock(return_value=error_text)), \
         patch.object(chat, "add_message_to_history", AsyncMock()) as add_hist, \
         patch.object(chat, "add_bonus_messages", AsyncMock()) as add_bonus, \
         patch.object(chat, "update_user", AsyncMock()) as upd_user:
        await chat.handle_text_message(message)

    # Пользовательское сообщение в историю пишется как обычно, но ответ ассистента — нет
    assistant_writes = [c for c in add_hist.await_args_list if c.args[1:2] == ("assistant",)]
    assert assistant_writes == []
    add_bonus.assert_not_awaited()
    upd_user.assert_not_awaited()
    assert user.chat_count == 0

    message.answer.assert_awaited_once()
    sent_text = message.answer.await_args.args[0]
    assert "Попробуйте ещё раз" in sent_text
    assert error_text not in sent_text


@pytest.mark.asyncio
async def test_chat_success_spends_limit_and_writes_history():
    from handlers import chat

    user = _chat_user()
    message = _make_chat_message()

    with patch.object(chat, "get_or_create_user", AsyncMock(return_value=user)), \
         patch.object(chat, "can_use_chat", return_value=True), \
         patch.object(chat, "ask_claude", AsyncMock(return_value="Сажайте хосты и папоротники.")), \
         patch.object(chat, "add_message_to_history", AsyncMock()) as add_hist, \
         patch.object(chat, "update_user", AsyncMock()) as upd_user:
        await chat.handle_text_message(message)

    assistant_writes = [c for c in add_hist.await_args_list if c.args[1:2] == ("assistant",)]
    assert len(assistant_writes) == 1
    upd_user.assert_awaited_once()
    assert user.chat_count == 1


# ── photo.py ─────────────────────────────────────────────────────────────

def _make_photo_message(user_id=1288492012) -> MagicMock:
    msg = MagicMock()
    msg.from_user = SimpleNamespace(id=user_id, username="u", first_name="P")
    msg.caption = None
    msg.chat = MagicMock(id=user_id)
    msg.answer = AsyncMock()
    processing = MagicMock()
    processing.delete = AsyncMock()
    msg.answer.return_value = processing
    msg.bot = MagicMock()
    msg.bot.send_chat_action = AsyncMock()
    msg.bot.get_file = AsyncMock(return_value=MagicMock(file_path="x"))

    class _Bytes:
        def read(self):
            return b"jpeg-bytes"

    msg.bot.download_file = AsyncMock(return_value=_Bytes())
    photo = MagicMock(file_id="fid1")
    msg.photo = [photo]
    return msg


def _photo_user(**kw):
    base = dict(telegram_id=1288492012, photo_count=0)
    base.update(kw)
    return SimpleNamespace(**base)


@pytest.mark.asyncio
@pytest.mark.parametrize("error_text", ERROR_TEXTS)
async def test_photo_error_does_not_save_or_spend_limit(error_text):
    from handlers import photo

    user = _photo_user()
    message = _make_photo_message()

    with patch.object(photo, "get_or_create_user", AsyncMock(return_value=user)), \
         patch.object(photo, "can_use_photo", return_value=True), \
         patch.object(photo, "ask_claude_with_image", AsyncMock(return_value=error_text)), \
         patch.object(photo, "save_diagnosis", AsyncMock()) as save_diag, \
         patch.object(photo, "update_user", AsyncMock()) as upd_user:
        await photo.handle_photo(message)

    save_diag.assert_not_awaited()
    upd_user.assert_not_awaited()
    assert user.photo_count == 0

    # Второй answer (после "Анализирую...") — предложение повторить, не текст ошибки
    assert message.answer.await_count == 2
    final_text = message.answer.await_args.args[0]
    assert "Попробуйте ещё раз" in final_text
    assert error_text not in final_text


@pytest.mark.asyncio
async def test_photo_success_saves_and_spends_limit():
    from handlers import photo

    user = _photo_user()
    message = _make_photo_message()

    with patch.object(photo, "get_or_create_user", AsyncMock(return_value=user)), \
         patch.object(photo, "can_use_photo", return_value=True), \
         patch.object(photo, "ask_claude_with_image", AsyncMock(return_value="Похоже на мучнистую росу.")), \
         patch.object(photo, "save_diagnosis", AsyncMock()) as save_diag, \
         patch.object(photo, "update_user", AsyncMock()) as upd_user:
        await photo.handle_photo(message)

    save_diag.assert_awaited_once()
    upd_user.assert_awaited_once()
    assert user.photo_count == 1


# ── plants.py ────────────────────────────────────────────────────────────

def _make_plants_callback(user_id=1288492012) -> MagicMock:
    cb = MagicMock()
    cb.data = "light:sun"
    cb.from_user = SimpleNamespace(id=user_id, username="u", first_name="P")
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    return cb


class _FakeState:
    def __init__(self, data):
        self._data = dict(data)
        self.cleared = False

    async def get_data(self):
        return self._data

    async def update_data(self, **kw):
        self._data.update(kw)

    async def clear(self):
        self.cleared = True


def _plants_user(**kw):
    base = dict(telegram_id=1288492012, plants_count=0)
    base.update(kw)
    return SimpleNamespace(**base)


@pytest.mark.asyncio
@pytest.mark.parametrize("error_text", ERROR_TEXTS)
async def test_plants_error_does_not_spend_limit(error_text):
    from handlers import plants

    user = _plants_user()
    state = _FakeState({"region": "Москва", "plant_type": "Цветники"})
    callback = _make_plants_callback()

    with patch.object(plants, "get_or_create_user", AsyncMock(return_value=user)), \
         patch.object(plants, "select_plants", AsyncMock(return_value=error_text)), \
         patch.object(plants, "update_user", AsyncMock()) as upd_user:
        await plants.cb_light(callback, state)

    upd_user.assert_not_awaited()
    assert user.plants_count == 0

    final_text = callback.message.edit_text.await_args.args[0]
    assert "Попробуйте ещё раз" in final_text
    assert error_text not in final_text


@pytest.mark.asyncio
async def test_plants_success_spends_limit():
    from handlers import plants

    user = _plants_user()
    state = _FakeState({"region": "Москва", "plant_type": "Цветники"})
    callback = _make_plants_callback()

    with patch.object(plants, "get_or_create_user", AsyncMock(return_value=user)), \
         patch.object(plants, "select_plants", AsyncMock(return_value="1. Хоста ...")), \
         patch.object(plants, "update_user", AsyncMock()) as upd_user:
        await plants.cb_light(callback, state)

    upd_user.assert_awaited_once()
    assert user.plants_count == 1
    final_text = callback.message.edit_text.await_args.args[0]
    assert "Подборка растений готова" in final_text
