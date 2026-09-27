"""PDF плана участка: кириллица читаема (встроенный DejaVu), без сырой markdown-разметки и эмодзи."""
import io
import logging
import re
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pypdf = pytest.importorskip("pypdf")

from handlers import plan  # noqa: E402
from services import pdf_generator  # noqa: E402

SAMPLE_PLAN = """# 🌲 План природного сада 6 соток

## 🗺 ЗОНИРОВАНИЕ

**1. Входная зона (15%)** — естественная композиция из кустарников у калитки

**2. Зона отдыха (20%)** — деревянный настил, окружённый миксбордером

---

## 💰 БЮДЖЕТ

- **Посадочный материал** — 40 000 р.
- **Резерв** — 5 000 р.

---

## 📋 С ЧЕГО НАЧАТЬ

**Шаг 1** → Разметьте зоны колышками и верёвкой

Для детального проекта нажмите кнопку **«Заказать проект»** ниже. 🌿
"""


def _make_pdf(plan_text=SAMPLE_PLAN):
    return pdf_generator.generate_plan_pdf(
        plan_text=plan_text, user_name="Petr", area="6", style="природный", designer_name="Garden Group",
    )


def _text(pdf: bytes) -> str:
    return "\n".join(p.extract_text() for p in pypdf.PdfReader(io.BytesIO(pdf)).pages)


def _fonts(pdf: bytes) -> list[tuple[str, bool]]:
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


def test_cyrillic_from_input_is_in_extracted_text():
    text = _text(_make_pdf())
    for phrase in ("ПЛАН САДА", "природный", "Входная зона", "Посадочный материал", "Заказать проект", "С ЧЕГО НАЧАТЬ"):
        assert phrase in text, phrase
    assert "■" not in text
    assert "Petr" in text and "Garden Group" in text and "40 000" in text  # латиница и цифры на месте


def test_dejavu_is_embedded():
    fonts = _fonts(_make_pdf())
    assert any("DejaVuSans" in name and embedded for name, embedded in fonts), fonts


def test_no_raw_markdown_and_no_emoji():
    text = _text(_make_pdf())
    assert "**" not in text
    assert not any(line.strip() == "---" for line in text.splitlines())
    assert not re.search("[\U0001F000-\U0001FAFF☀-➿]", text)


def test_user_name_with_emoji_and_markup_chars_does_not_break_pdf():
    pdf = pdf_generator.generate_plan_pdf(
        plan_text="ОК", user_name="Аня 🌿 <b>&", area="6", style="кантри", designer_name="Garden Group",
    )
    assert "Аня" in _text(pdf) and pdf.startswith(b"%PDF")


def _unavailable_fonts(monkeypatch, tmp_path):
    monkeypatch.setattr(pdf_generator, "FONTS_DIR", tmp_path)  # пустая папка: файлов шрифта нет
    monkeypatch.setattr(pdf_generator.pdfmetrics, "getRegisteredFontNames", lambda: [])


def test_missing_font_raises_and_logs_instead_of_making_a_squares_pdf(monkeypatch, tmp_path, caplog):
    _unavailable_fonts(monkeypatch, tmp_path)
    with caplog.at_level(logging.ERROR, logger="services.pdf_generator"), pytest.raises(pdf_generator.PdfFontError):
        _make_pdf()
    msgs = " ".join(r.getMessage() for r in caplog.records if r.levelno >= logging.ERROR)
    assert "DejaVuSans" in msgs and str(tmp_path) in msgs  # какой шрифт и какой путь


@pytest.mark.asyncio
async def test_plan_generate_skips_pdf_but_sends_plan_when_font_is_missing(monkeypatch, tmp_path, caplog):
    _unavailable_fonts(monkeypatch, tmp_path)
    state = MagicMock()
    state.get_state = AsyncMock(return_value=plan.PlanForm.waiting_confirm.state)
    state.get_data = AsyncMock(return_value={"area": "6", "style": "природный", "budget": "до 100к", "wishes": "ТЕСТ"})
    state.clear = AsyncMock()
    callback = MagicMock()
    callback.answer = AsyncMock()
    callback.from_user = SimpleNamespace(id=1, username="u", first_name="P", full_name="P U")
    callback.message.edit_text = AsyncMock()
    callback.message.answer = AsyncMock()
    callback.message.answer_document = AsyncMock()
    callback.message.bot.send_chat_action = AsyncMock()
    callback.message.chat.id = 1

    with patch.object(plan, "ask_claude", AsyncMock(return_value=SAMPLE_PLAN)), \
         patch.object(plan, "save_order", AsyncMock(return_value=31)), \
         patch.object(plan, "get_or_create_user", AsyncMock()), \
         patch.object(plan, "_notify_designer", AsyncMock()), \
         patch.object(plan, "get_designer_qualification_line", AsyncMock(return_value="q")), \
         caplog.at_level(logging.WARNING):
        await plan._plan_generate(callback, state)  # исключение не вылетает

    callback.message.answer.assert_awaited()  # сообщение с планом ушло
    callback.message.answer_document.assert_not_awaited()  # PDF не отправлен
    assert any("PDF" in r.getMessage() for r in caplog.records)


@pytest.mark.asyncio
async def test_plan_generate_sends_readable_pdf_when_font_is_available():
    state = MagicMock()
    state.get_state = AsyncMock(return_value=plan.PlanForm.waiting_confirm.state)
    state.get_data = AsyncMock(return_value={"area": "6", "style": "природный", "budget": "до 100к", "wishes": "ТЕСТ"})
    state.clear = AsyncMock()
    callback = MagicMock()
    callback.answer = AsyncMock()
    callback.from_user = SimpleNamespace(id=1, username="u", first_name="P", full_name="Petr")
    callback.message.edit_text = AsyncMock()
    callback.message.answer = AsyncMock()
    callback.message.answer_document = AsyncMock()
    callback.message.bot.send_chat_action = AsyncMock()
    callback.message.chat.id = 1

    with patch.object(plan, "ask_claude", AsyncMock(return_value=SAMPLE_PLAN)), \
         patch.object(plan, "save_order", AsyncMock(return_value=31)), \
         patch.object(plan, "get_or_create_user", AsyncMock()), \
         patch.object(plan, "_notify_designer", AsyncMock()), \
         patch.object(plan, "get_designer_qualification_line", AsyncMock(return_value="q")):
        await plan._plan_generate(callback, state)

    callback.message.answer_document.assert_awaited_once()
    sent = callback.message.answer_document.await_args.args[0]
    assert sent.data.startswith(b"%PDF") and "Входная зона" in _text(sent.data)

# ── геометрия обложки и линий (PyMuPDF): линия не должна пересекать текст ────────────────────────────
def _geometry(pdf: bytes):
    """[(page_no, words[(x0,y0,x1,y1,word)], hlines[(x0,x1,y,width)])]"""
    pymupdf = pytest.importorskip("pymupdf")
    out = []
    doc = pymupdf.open(stream=pdf, filetype="pdf")
    for no, page in enumerate(doc, 1):
        lines = []
        for d in page.get_drawings():
            for it in d["items"]:
                if it[0] == "l" and abs(it[1].y - it[2].y) < 0.5 and abs(it[1].x - it[2].x) > 5:
                    lines.append((min(it[1].x, it[2].x), max(it[1].x, it[2].x), it[1].y, d.get("width") or 0))
                elif it[0] == "re" and it[1].height < 3 and it[1].width > 5:
                    r = it[1]
                    lines.append((r.x0, r.x1, (r.y0 + r.y1) / 2, r.height))
        out.append((no, [w[:5] for w in page.get_text("words")], lines))
    return out


def _crossings(words, lines):
    hits = []
    for x0, x1, y, w in lines:
        for wd in words:
            if wd[0] < x1 and wd[2] > x0 and wd[1] - w / 2 < y < wd[3] + w / 2:
                hits.append((wd[4], round(y, 2), round(wd[1], 2), round(wd[3], 2)))
    return hits


def test_cover_rule_does_not_cross_the_title_and_keeps_a_gap():
    pages = _geometry(_make_pdf())
    no, words, lines = pages[0]
    title = [w for w in words if w[4] in ("ПЛАН", "САДА")]
    assert len(title) == 2
    assert _crossings(words, lines) == []
    title_bottom = max(w[3] for w in title)
    below = [y for _, _, y, _ in lines if y >= title_bottom]  # линия под заголовком
    assert below, "под заголовком обложки нет линии"
    assert min(below) - title_bottom >= 6.0, (min(below), title_bottom)


def test_no_horizontal_line_crosses_any_word_on_any_page():
    pdf = _make_pdf("\n\n".join([SAMPLE_PLAN] * 3))  # длинный образец: несколько страниц
    pages = _geometry(pdf)
    assert len(pages) >= 3
    for no, words, lines in pages:
        assert _crossings(words, lines) == [], f"page {no}"


def test_cover_title_leading_is_at_least_1_2_of_font_size():
    assert pdf_generator.COVER_TITLE_LEADING >= 1.2 * pdf_generator.COVER_TITLE_SIZE
