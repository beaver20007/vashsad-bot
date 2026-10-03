"""Общее форматирование дат для записи на консультацию (handlers/booking.py и
services/scheduler.py) — отдельный модуль, чтобы они не импортировали друг друга
на уровне модуля (booking.py уже делает локальный импорт scheduler внутри функций,
а scheduler.py теперь тоже обращается к booking_id/БД — общий форматтер снимает
необходимость решать, кто у кого одалживает эти функции).

Везде ниже на вход — наивный datetime/date, трактуется как московское настенное
время (см. docs/ORCHESTRATOR.md, трек часового пояса от 2026-10-03).
"""
from datetime import date, datetime

_MONTHS = ["янв", "фев", "мар", "апр", "май", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"]
_WEEKDAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]


def ru_dt_label(dt: datetime) -> str:
    """'12 окт в 10:00'"""
    return f"{dt.day} {_MONTHS[dt.month - 1]} в {dt.strftime('%H:%M')}"


def ru_dt_label_short(dt: datetime) -> str:
    """'12 окт 10:00'"""
    return f"{dt.day} {_MONTHS[dt.month - 1]} {dt.strftime('%H:%M')}"


def ru_day_label(d: date) -> str:
    """'Пн, 12 окт'"""
    return f"{_WEEKDAYS[d.weekday()]}, {d.day} {_MONTHS[d.month - 1]}"
