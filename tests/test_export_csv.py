"""CSV-экспорт заявок: колонка цены подписана по содержимому (service_price), не «Бюджет»."""
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from handlers import export


@pytest.mark.asyncio
async def test_csv_price_column_is_labelled_by_content(monkeypatch):
    monkeypatch.setenv("DESIGNER_TELEGRAM_ID", "42")
    row = {
        "id": 1, "telegram_id": 7, "service_type": "Проект участка", "status": "new",
        "created_at": None, "contact_phone": "+70000000000", "service_price": 3500,
    }
    conn = MagicMock()
    conn.fetch = AsyncMock(return_value=[row])
    pool = MagicMock()

    @asynccontextmanager
    async def acquire():
        yield conn

    pool.acquire = acquire

    sent = {}

    async def answer_document(file, caption=None):
        sent["data"] = file.data.decode("utf-8-sig")

    callback = MagicMock()
    callback.data = "csv:all"
    callback.from_user = SimpleNamespace(id=42)
    callback.answer = AsyncMock()
    callback.message.answer_document = answer_document

    with patch("handlers.export.get_pool", new_callable=AsyncMock, return_value=pool):
        await export.cb_csv(callback)

    header, line = sent["data"].splitlines()[:2]
    assert "Бюджет" not in header
    assert header.split(";")[-1] == "Цена услуги, ₽"
    assert line.split(";")[-1] == "3500"
    assert "budget_range" not in conn.fetch.call_args.args[0]
