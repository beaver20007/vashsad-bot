"""services/bot_texts.py: БД поверх файла-дефолта, тексты не живут литералами в коде."""
import asyncio
import pathlib
import re

import pytest

from services import bot_texts


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    monkeypatch.setattr(bot_texts, "_db_rows", {})
    monkeypatch.setattr(bot_texts, "_warned", set())


def test_defaults_file_has_all_required_keys():
    keys = set(bot_texts.all_keys()["bot_text"])
    assert {"system_prompt.chat", "system_prompt.vision", "faq", "seasonal_messages", "i18n", "onboarding"} <= keys


def test_db_value_overrides_default(monkeypatch):
    monkeypatch.setattr(bot_texts, "_db_rows", {"system_prompt.chat": {"text": "из БД"}})
    assert bot_texts.get("system_prompt.chat")["text"] == "из БД"


def test_default_used_when_db_empty():
    assert "ВашСад" in bot_texts.get("system_prompt.chat")["text"]


def test_unknown_key_raises():
    with pytest.raises(KeyError):
        bot_texts.get("no.such.key")


def test_load_reads_rows_from_content_strings(monkeypatch):
    class Conn:
        async def fetch(self, sql, ns):
            assert ns == "bot_text"
            return [{"key": "onboarding", "value": '{"region_prompt": "X"}'}]

    class Acq:
        async def __aenter__(self):
            return Conn()

        async def __aexit__(self, *a):
            return False

    class Pool:
        def acquire(self):
            return Acq()

    async def fake_get_pool():
        return Pool()

    import services.database as db
    monkeypatch.setattr(db, "get_pool", fake_get_pool)
    asyncio.run(bot_texts.load())
    assert bot_texts.get("onboarding")["region_prompt"] == "X"


def test_load_failure_keeps_defaults(monkeypatch):
    async def boom():
        raise RuntimeError("no db")

    import services.database as db
    monkeypatch.setattr(db, "get_pool", boom)
    asyncio.run(bot_texts.load())
    assert bot_texts.get("faq")["items"]


def test_faq_and_i18n_work_through_defaults():
    from handlers.chat import check_faq
    from services.i18n import t
    assert check_faq("сколько стоит проект") is not None
    assert "{bot_name}" in t("welcome_a", "ru")


def test_no_text_literals_left_in_code():
    """SYSTEM_PROMPT/FAQ_PATTERNS/SEASONAL_MESSAGES больше не определены в коде."""
    root = pathlib.Path(__file__).resolve().parent.parent
    pattern = re.compile(r"^(SYSTEM_PROMPT|FAQ_PATTERNS|SEASONAL_MESSAGES|STRINGS)\s*(:[^=]*)?=", re.M)
    for path in list(root.glob("handlers/*.py")) + list(root.glob("services/*.py")):
        assert not pattern.search(path.read_text(encoding="utf-8")), path.name
