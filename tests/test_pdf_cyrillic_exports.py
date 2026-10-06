"""Кириллица в четырёх PDF-выгрузках бота (guide/clients/favorites/orders) — до этого трека
только generate_plan_pdf использовал встроенный DejaVu Sans (PR #47), остальные три рисовали
кириллицу стандартным Helvetica (чёрные квадраты вместо букв, т.к. у Helvetica нет кириллических
глифов). Единый помощник _ensure_fonts/PDF_FONT/PDF_FONT_BOLD из services/pdf_generator
зарегистрирован один раз и используется во всех четырёх генераторах без копипасты.

pypdf — уже тестовая зависимость (requirements-dev.txt, используется в test_plan_pdf.py с PR #47),
новую зависимость не добавляем.
"""
import io
from datetime import datetime

import pytest

pypdf = pytest.importorskip("pypdf")

from handlers import export  # noqa: E402
from services import pdf_generator  # noqa: E402


def _text(pdf: bytes) -> str:
    return "\n".join(p.extract_text() for p in pypdf.PdfReader(io.BytesIO(pdf)).pages)


def _fonts(pdf: bytes) -> list[tuple[str, bool]]:
    """[(base_font_name, embedded)] — та же проверка, что в test_plan_pdf.py."""
    found = set()
    for page in pypdf.PdfReader(io.BytesIO(pdf)).pages:
        for f in page["/Resources"].get_object().get("/Font", {}).get_object().values():
            f = f.get_object()
            desc = f.get("/FontDescriptor")
            if desc is None:
                for df in f.get("/DescendantFonts", []) or []:
                    desc = df.get_object().get("/FontDescriptor")
            keys = ("/FontFile", "/FontFile2", "/FontFile3")
            embedded = desc is not None and any(k in desc.get_object() for k in keys)
            found.add((str(f.get("/BaseFont")), embedded))
    return sorted(found)


def _assert_dejavu_pdf_with_cyrillic(pdf: bytes, phrases: list[str]):
    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 500  # не пустой/обрезанный документ
    fonts = _fonts(pdf)
    assert any("DejaVuSans" in name and embedded for name, embedded in fonts), fonts
    text = _text(pdf)
    for phrase in phrases:
        assert phrase in text, (phrase, text)
    assert "■" not in text  # типичный символ-заглушка для отсутствующего глифа


# ── guide (services/pdf_generator.generate_guide_pdf) ──────────────────────

def test_guide_pdf_uses_embedded_dejavu_and_renders_cyrillic():
    pdf = pdf_generator.generate_guide_pdf(designer_name="Иван Петров", qualification_line="Дипломированный дизайнер")
    _assert_dejavu_pdf_with_cyrillic(pdf, [
        "ВашСад", "растений для природного сада", "Нижегородская и Владимирская области",
        "Иван Петров", "Деревья", "Хоста Blue Angel",
    ])


# ── clients (services/pdf_generator.generate_clients_pdf) ───────────────────

def test_clients_pdf_uses_embedded_dejavu_and_renders_cyrillic():
    clients_data = [
        {
            "name": "Клиент Тестовый", "phone": "+7 900 000-00-00", "service_type": "Ландшафтный дизайн",
            "region": "Нижегородская область", "status": "in_progress", "created_at": datetime(2026, 9, 1),
        },
    ]
    pdf = pdf_generator.generate_clients_pdf(clients_data, designer_name="Мария Садовая")
    # ячейки таблицы режутся по длине (row.get("region")[:16] и т.п. в generate_clients_pdf) —
    # проверяем читаемый кириллический текст, а не точное совпадение с несрезанным исходником.
    _assert_dejavu_pdf_with_cyrillic(pdf, [
        "Клиенты ВашСад", "Мария Садовая", "Клиент Тестовый", "Ландшафтный дизайн",
        "Нижегородская об", "В работе",
    ])


def test_clients_pdf_empty_list_still_uses_dejavu():
    pdf = pdf_generator.generate_clients_pdf([], designer_name="Мария Садовая")
    _assert_dejavu_pdf_with_cyrillic(pdf, ["Клиентов пока нет"])


# ── favorites (handlers/export._build_favorites_pdf) ────────────────────────

def test_favorites_pdf_uses_embedded_dejavu_and_renders_cyrillic():
    rows = [
        {
            "name": "Хоста Blue Angel", "location": "Тенистый уголок у забора",
            "notes": "Полив раз в неделю, мульчирование", "added_at": datetime(2026, 8, 15),
        },
    ]
    pdf = export._build_favorites_pdf(rows, qualification_line="Дипломированный ландшафтный дизайнер")
    _assert_dejavu_pdf_with_cyrillic(pdf, [
        "Мои растения", "Хоста Blue Angel", "Тенистый уголок у забора",
        "Полив раз в неделю, мульчирование", "Дипломированный ландшафтный дизайнер",
    ])


# ── orders (handlers/export._build_pdf) ─────────────────────────────────────

def test_orders_pdf_uses_embedded_dejavu_and_renders_cyrillic():
    rows = [
        {
            "id": 1, "created_at": datetime(2026, 9, 10), "first_name": "Анна Клиентова",
            "service_name": "Проект благоустройства участка", "status": "done",
            "phone": "+7 900 123-45-67", "service_price": 50000,
        },
    ]
    pdf = export._build_pdf(rows, "30 дней")
    # "Клиент" (r["first_name"][:12]) режется по длине в _build_pdf — проверяем читаемый
    # кириллический текст, а не точное совпадение с несрезанным исходником.
    _assert_dejavu_pdf_with_cyrillic(pdf, [
        "Отчёт по заявкам", "Анна Клиенто", "Проект благоустройства участка", "Выполнена",
    ])


def test_orders_pdf_empty_rows_still_uses_dejavu():
    pdf = export._build_pdf([], "7 дней")
    _assert_dejavu_pdf_with_cyrillic(pdf, ["Заявок за этот период нет"])


# ── Шрифт регистрируется один раз, помощник общий (без копипасты) ──────────

def test_all_four_generators_use_the_same_font_helper():
    """Явная проверка «единым помощником»: все четыре генератора полагаются
    на один и тот же services.pdf_generator._ensure_fonts/PDF_FONT/PDF_FONT_BOLD,
    а не на свою копию регистрации шрифта."""
    assert export.PDF_FONT == pdf_generator.PDF_FONT == "DejaVuSans"
    assert export.PDF_FONT_BOLD == pdf_generator.PDF_FONT_BOLD == "DejaVuSans-Bold"
    assert export._ensure_pdf_fonts is pdf_generator._ensure_fonts
