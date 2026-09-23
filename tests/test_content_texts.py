"""Подстановка {service} в тексте статуса заявки (services/content_texts.py)."""
import asyncio

import pytest

from services import content_texts

IN_PROGRESS_ROW = {
    "notify_text": "Мы уже работаем над Вашим {service} и скоро отправим его Вам!",
    "client_label": "В работе у дизайнера",
    "service_words": {"project": "проектом", "container": "контейнерным озеленением", "flowerbed": "цветником"},
}


def _patch_row(monkeypatch, row):
    async def fake_get_value(namespace, key):
        assert namespace == "order_status"
        return row

    monkeypatch.setattr(content_texts, "get_value", fake_get_value)


def _run(coro):
    return asyncio.run(coro)


@pytest.mark.parametrize("service_type,expected", [
    ("custom_flowerbed", "flowerbed"),
    ("flowerbed", "flowerbed"),
    ("container_garden", "container"),
    ("CONTAINER", "container"),
    ("concept", "project"),
    ("project", "project"),
    ("plan", "project"),
    ("consult", "project"),
    (None, "project"),
    ("", "project"),
])
def test_order_service_category(service_type, expected):
    assert content_texts.order_service_category(service_type) == expected


@pytest.mark.parametrize("service_type,word", [
    ("concept", "проектом"),
    ("plan", "проектом"),
    ("custom_flowerbed", "цветником"),
    ("container_garden", "контейнерным озеленением"),
])
def test_in_progress_substitutes_word(monkeypatch, service_type, word):
    _patch_row(monkeypatch, IN_PROGRESS_ROW)
    text = _run(content_texts.get_order_status_text("in_progress", service_type))
    assert text == f"Мы уже работаем над Вашим {word} и скоро отправим его Вам!"
    assert "{service}" not in text


def test_missing_word_falls_back_instead_of_raw_placeholder(monkeypatch):
    row = dict(IN_PROGRESS_ROW, service_words={"project": "проектом"})
    _patch_row(monkeypatch, row)
    assert _run(content_texts.get_order_status_text("in_progress", "custom_flowerbed")) is None


def test_no_row_returns_none(monkeypatch):
    _patch_row(monkeypatch, None)
    assert _run(content_texts.get_order_status_text("in_progress", "concept")) is None


def test_text_without_placeholder_returned_as_is(monkeypatch):
    _patch_row(monkeypatch, {"notify_text": "Пожалуйста, оставьте отзыв в приложении."})
    assert _run(content_texts.get_order_status_text("done", "concept")) == "Пожалуйста, оставьте отзыв в приложении."


def test_canceled_not_read_from_content(monkeypatch):
    _patch_row(monkeypatch, {"notify_text": "не должно использоваться"})
    assert _run(content_texts.get_order_status_text("canceled", "concept")) is None
