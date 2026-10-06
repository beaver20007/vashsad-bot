"""B1 (ночной бриф 05→06.10.2026): по brief-у остальные PDF (гид/клиенты/
избранное/заказы) должны были использовать Helvetica без кириллицы — на
дереве origin/fix/pdf-cyrillic (PR #56, уже чинит все четыре через DejaVu,
plan.py — DejaVu с PR #47) это уже не так: проверено вручную (`git grep
Helvetica` на этом дереве не находит ни одного живого использования в коде,
только в комментариях/докстрингах; у каждого из 28 ParagraphStyle в
services/pdf_generator.py и handlers/export.py есть явный fontName=PDF_FONT/
PDF_FONT_BOLD). Новых генераторов чинить не из чего.

Этот файл добавляет единственное, чего не было: регрессионную проверку НА
УРОВНЕ РЕАЛЬНОГО ПОСТРОЕНИЯ стилей (а не только на тексте финального PDF, как
в test_pdf_cyrillic_exports.py) — если кто-то в будущем добавит новый
ParagraphStyle без fontName (= унаследует Helvetica от SampleStyleSheet), этот
тест упадёт даже если сам текст в этом месте не кириллический и не попал бы
под проверку "нет квадратов-заглушек" в существующих тестах.
"""
import os
import sys
from datetime import datetime
from unittest.mock import patch

from reportlab.lib.styles import ParagraphStyle

from handlers import export
from services import pdf_generator

HELVETICA_PREFIXES = ("Helvetica", "Courier", "Times")  # встроенные PDF-шрифты без кириллицы

# reportlab.getSampleStyleSheet() сам создаёт ~15 встроенных ParagraphStyle
# (Normal/Title/Heading1.../BodyText...) на базовом Helvetica — это нормально,
# в них кириллицу никто не пишет. Нас интересуют ТОЛЬКО стили, которые явно
# создаёт сам наш код (services/pdf_generator.py, handlers/export.py) — в т.ч.
# те, что намеренно переиспользуют имя встроенного стиля (например "Title"),
# поэтому фильтруем не по имени стиля, а по файлу, откуда вызван ParagraphStyle(...).
_OUR_FILES = {
    os.path.normcase(os.path.abspath(pdf_generator.__file__)),
    os.path.normcase(os.path.abspath(export.__file__)),
}


def _collect_fontnames(build_fn):
    seen: list[str] = []
    orig_init = ParagraphStyle.__init__

    def _spy(self, *a, **kw):
        orig_init(self, *a, **kw)
        caller_file = os.path.normcase(os.path.abspath(sys._getframe(1).f_code.co_filename))
        if caller_file in _OUR_FILES:
            seen.append(self.fontName)

    with patch.object(ParagraphStyle, "__init__", _spy):
        build_fn()
    return seen


def test_plan_pdf_styles_never_fall_back_to_builtin_fonts():
    fontnames = _collect_fontnames(lambda: pdf_generator.generate_plan_pdf(
        plan_text="Зонирование участка.\nРастения: хоста, роза.",
        user_name="Тест Тестов", area="6", style="природный",
        designer_name="Иван", qualification_line="Дизайнер",
    ))
    assert fontnames, "ParagraphStyle не создавался — тест не сработал"
    assert not any(f.startswith(HELVETICA_PREFIXES) for f in fontnames), fontnames


def test_guide_pdf_styles_never_fall_back_to_builtin_fonts():
    fontnames = _collect_fontnames(lambda: pdf_generator.generate_guide_pdf(
        designer_name="Иван", qualification_line="Дизайнер",
    ))
    assert fontnames
    assert not any(f.startswith(HELVETICA_PREFIXES) for f in fontnames), fontnames


def test_clients_pdf_styles_never_fall_back_to_builtin_fonts():
    fontnames = _collect_fontnames(lambda: pdf_generator.generate_clients_pdf(
        [{"name": "Клиент", "phone": "+7", "service_type": "x", "region": "x",
          "status": "new", "created_at": datetime(2026, 1, 1)}],
        designer_name="Иван",
    ))
    assert fontnames
    assert not any(f.startswith(HELVETICA_PREFIXES) for f in fontnames), fontnames


def test_favorites_pdf_styles_never_fall_back_to_builtin_fonts():
    fontnames = _collect_fontnames(lambda: export._build_favorites_pdf(
        [{"name": "Растение", "location": "x", "notes": "x", "added_at": datetime(2026, 1, 1)}],
        qualification_line="Дизайнер",
    ))
    assert fontnames
    assert not any(f.startswith(HELVETICA_PREFIXES) for f in fontnames), fontnames


def test_orders_pdf_styles_never_fall_back_to_builtin_fonts():
    fontnames = _collect_fontnames(lambda: export._build_pdf(
        [{"id": 1, "created_at": datetime(2026, 1, 1), "first_name": "Клиент",
          "service_name": "x", "status": "new", "phone": "+7", "service_price": 1000}],
        "7 дней",
    ))
    assert fontnames
    assert not any(f.startswith(HELVETICA_PREFIXES) for f in fontnames), fontnames
