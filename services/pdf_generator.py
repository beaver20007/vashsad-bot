"""
services/pdf_generator.py
Генерация PDF-гайда «15 растений для природного сада НО» через ReportLab.
"""
import io
import logging
import re
from pathlib import Path

from reportlab.lib.colors import HexColor, white
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from config import DESIGNER_NAME
from services.content_texts import DEFAULT_QUALIFICATION_LINE

# ── Цветовая палитра ──
SAGE   = HexColor("#4A6B50")
EARTH  = HexColor("#8B6F47")
CREAM  = HexColor("#F9F7F3")
DARK   = HexColor("#2C2418")
LIGHT  = HexColor("#E8F0E9")

PLANTS_DATA = [
    ("Береза повислая",     "Betula pendula",    "Деревья",      "Полное солнце / тень",   "Редкий",    "З. 3",  "Лёгкая ажурная крона, весенние серёжки, белая кора. Создаёт природный акцент."),
    ("Рябина обыкновенная", "Sorbus aucuparia",  "Деревья",      "Солнце / полутень",      "Умеренный", "З. 3",  "Ягоды для птиц, яркая осенняя окраска, устойчивость к морозам."),
    ("Яблоня Антоновка",    "Malus domestica",   "Деревья",      "Солнце",                 "Умеренный", "З. 3",  "Классический плодовый сорт, ароматные плоды, декоративное цветение."),
    ("Черёмуха обыкновен.", "Prunus padus",      "Деревья",      "Полутень / тень",        "Умеренный", "З. 3",  "Душистые белые кисти, теневыносливость, ранний медонос."),
    ("Сирень обыкновенная", "Syringa vulgaris",  "Кустарники",   "Солнце",                 "Умеренный", "З. 3",  "Ароматные соцветия, неприхотливость, долголетие до 100 лет."),
    ("Калина обыкновенная", "Viburnum opulus",   "Кустарники",   "Солнце / полутень",      "Умеренный", "З. 3",  "Зонтики белых цветков, красные ягоды осенью, для влажных мест."),
    ("Шиповник майский",    "Rosa majalis",      "Кустарники",   "Солнце",                 "Редкий",    "З. 3",  "Ароматные розовые цветки, плоды богаты вит. C, живые изгороди."),
    ("Смородина золотая",   "Ribes aureum",      "Кустарники",   "Солнце / полутень",      "Умеренный", "З. 3",  "Жёлтые душистые цветки, съедобные ягоды, осенний пурпур листвы."),
    ("Хоста Blue Angel",    "Hosta sieboldiana", "Многолетники", "Полутень / тень",        "Умеренный", "З. 3",  "Огромные сизо-голубые листья, идеальна под деревьями."),
    ("Астильба Фанал",      "Astilbe arendsii",  "Многолетники", "Полутень",               "Умеренный", "З. 4",  "Тёмно-красные метёлки, декоративна весь сезон."),
    ("Герань луговая",      "Geranium pratense", "Многолетники", "Солнце / полутень",      "Редкий",    "З. 3",  "Фиолетово-голубые цветки, почвопокровная, самосев."),
    ("Манжетка мягкая",     "Alchemilla mollis", "Многолетники", "Солнце / полутень",      "Умеренный", "З. 3",  "Резные листья удерживают капли росы, жёлто-зелёные цветки."),
    ("Анемона осенняя",     "Anemone hupehensis","Многолетники", "Полутень",               "Умеренный", "З. 5",  "Нежные розово-белые цветки в конце лета, природный стиль."),
    ("Вербейник монетный",  "Lysimachia nummularia","Почвопокровные","Полутень / тень",    "Умеренный", "З. 4",  "Золотистая форма Aurea украшает тенистые уголки."),
    ("Ирис сибирский",      "Iris sibirica",     "Многолетники", "Солнце / полутень",      "Редкий",    "З. 3",  "Фиолетово-синие цветки, узкие листья, влагостойкость."),
]


log = logging.getLogger(__name__)

# Кириллица в PDF плана: стандартный Helvetica её не содержит (буквы превращаются в чёрные квадраты),
# поэтому используется встроенный DejaVu Sans (лицензия — assets/fonts/LICENSE_DEJAVU). Путь — от модуля, не от cwd.
FONTS_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"
# обложка плана: интервал заголовка не меньше 1.2 кегля, иначе линия под ним (HRFlowable) ложится поверх текста
COVER_TITLE_SIZE = 28
COVER_TITLE_LEADING = 34
PDF_FONT = "DejaVuSans"
PDF_FONT_BOLD = "DejaVuSans-Bold"
_FONT_FILES = {PDF_FONT: "DejaVuSans.ttf", PDF_FONT_BOLD: "DejaVuSans-Bold.ttf"}

# эмодзи и служебные символы к ним (в чате остаются, в PDF шрифт их не содержит)
_EMOJI_RE = re.compile(
    "[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\u2300-\u23FF\uFE00-\uFE0F\u200D\u20E3\U000E0000-\U000E007F]+"
)
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_ITALIC_RE = re.compile(r"(?<!\*)\*(?=\S)(.+?)(?<=\S)\*(?!\*)")
_RULE_RE = re.compile(r"^\s*([-*_])\1{2,}\s*$")
_BULLET_RE = re.compile(r"^[-*+]\s+")


class PdfFontError(RuntimeError):
    """Кириллический шрифт недоступен: PDF не создаётся (иначе вместо букв были бы чёрные квадраты)."""


def _ensure_fonts() -> None:
    registered = set(pdfmetrics.getRegisteredFontNames())
    for name, filename in _FONT_FILES.items():
        if name in registered:
            continue
        path = FONTS_DIR / filename
        try:
            pdfmetrics.registerFont(TTFont(name, str(path)))
        except Exception as e:
            log.error("PDF: кириллический шрифт недоступен: %s, файл %s (%s) - PDF не создаётся", name, path, e)
            raise PdfFontError(f"font {name} unavailable at {path}: {e}") from e
    pdfmetrics.registerFontFamily(
        PDF_FONT, normal=PDF_FONT, bold=PDF_FONT_BOLD, italic=PDF_FONT, boldItalic=PDF_FONT_BOLD,
    )


def _clean(text: str) -> str:
    """Убрать эмодзи и схлопнуть пробелы."""
    return re.sub(r"[ \t]{2,}", " ", _EMOJI_RE.sub("", text or "")).strip()


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _plain(text: str) -> str:
    """Текст без markdown-меток (для решений вроде «это заголовок»)."""
    return _ITALIC_RE.sub(r"\1", _BOLD_RE.sub(r"\1", _clean(text))).replace("**", "")


def _inline(text: str) -> str:
    """Markdown ** -> жирный, лишние метки убрать, XML экранировать (для Paragraph)."""
    s = _escape(_clean(text))
    s = _BOLD_RE.sub(r"<b>\1</b>", s)
    s = _ITALIC_RE.sub(r"\1", s)
    return s.replace("**", "")


def _field(text: str) -> str:
    """Поле из ввода пользователя/конфига (имя, площадь, стиль): без эмодзи, экранированное."""
    return _escape(_clean(str(text)))


def generate_plan_pdf(
    plan_text: str,
    user_name: str,
    area: str,
    style: str,
    designer_name: str = DESIGNER_NAME,
    qualification_line: str = DEFAULT_QUALIFICATION_LINE,
) -> bytes:
    """Генерирует PDF план участка и возвращает байты.

    Бросает PdfFontError, если шрифт с кириллицей недоступен (вызывающий код ловит исключение и не отправляет PDF).
    """
    from datetime import date

    _ensure_fonts()

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=2*cm, rightMargin=2*cm,
        topMargin=2*cm, bottomMargin=2*cm,
    )

    styles = getSampleStyleSheet()

    cover_title_style = ParagraphStyle(
        "CoverTitle", parent=styles["Normal"],
        fontSize=COVER_TITLE_SIZE, leading=COVER_TITLE_LEADING, textColor=SAGE, alignment=TA_CENTER,
        fontName=PDF_FONT_BOLD, spaceAfter=8,
    )
    cover_sub_style = ParagraphStyle(
        "CoverSub", parent=styles["Normal"],
        fontSize=14, textColor=EARTH, alignment=TA_CENTER,
        fontName=PDF_FONT, spaceAfter=4,
    )
    cover_meta_style = ParagraphStyle(
        "CoverMeta", parent=styles["Normal"],
        fontSize=11, textColor=DARK, alignment=TA_CENTER,
        fontName=PDF_FONT, spaceAfter=4,
    )
    h1_style = ParagraphStyle(
        "PlanH1", parent=styles["Normal"],
        fontSize=14, textColor=SAGE, fontName=PDF_FONT_BOLD,
        spaceBefore=14, spaceAfter=6,
    )
    body_style = ParagraphStyle(
        "PlanBody", parent=styles["Normal"],
        fontSize=10, textColor=DARK, leading=15, spaceAfter=4,
        fontName=PDF_FONT,
    )
    footer_style = ParagraphStyle(
        "PlanFooter", parent=styles["Normal"],
        fontSize=8, textColor=EARTH, alignment=TA_CENTER,
        fontName=PDF_FONT,
    )

    story = []

    # ── Обложка ──────────────────────────────────────────────────
    story.append(Spacer(1, 2*cm))
    story.append(Paragraph("ПЛАН САДА", cover_title_style))
    story.append(HRFlowable(width="80%", thickness=2, color=SAGE, hAlign="CENTER"))
    story.append(Spacer(1, 0.5*cm))
    story.append(Paragraph(_field(user_name), cover_sub_style))
    story.append(Spacer(1, 0.4*cm))
    story.append(Paragraph(f"Площадь: {_field(area)} соток  ·  Стиль: {_field(style)}", cover_meta_style))
    story.append(Paragraph(f"Дата: {date.today().strftime('%d.%m.%Y')}", cover_meta_style))
    story.append(Spacer(1, 0.6*cm))
    story.append(Paragraph(f"Дизайнер: {_field(designer_name)}", cover_meta_style))
    story.append(Spacer(1, 2*cm))
    story.append(HRFlowable(width="100%", thickness=0.5, color=EARTH))
    story.append(Spacer(1, 0.3*cm))
    story.append(Paragraph(
        f"{_field(qualification_line)} · Природный стиль садов · "
        "Нижегородская и Владимирская области",
        footer_style,
    ))

    from reportlab.platypus import PageBreak
    story.append(PageBreak())

    # ── Содержание плана ─────────────────────────────────────────
    for raw_line in plan_text.splitlines():
        line = raw_line.strip()
        if not line:
            story.append(Spacer(1, 0.3*cm))
            continue

        # разделитель markdown (---, ***, ___) -> тонкая линия
        if _RULE_RE.match(line):
            story.append(HRFlowable(width="100%", thickness=0.4, color=EARTH, spaceBefore=4, spaceAfter=4))
            continue

        # Заголовок: строка начинается с # или это короткая строка ЗАГЛАВНЫМИ
        is_markdown_header = line.startswith("#")
        text = line.lstrip("#").strip() if is_markdown_header else _BULLET_RE.sub("\u2022 ", line)
        plain = _plain(text)
        if not plain:  # была одна разметка/эмодзи
            continue
        is_caps_header = (
            plain == plain.upper()
            and len(plain) <= 60
            and any(c.isalpha() for c in plain)
        )
        if is_markdown_header or is_caps_header:
            story.append(Paragraph(_inline(text), h1_style))
        else:
            story.append(Paragraph(_inline(text), body_style))

    # ── Подвал ───────────────────────────────────────────────────
    story.append(Spacer(1, 1*cm))
    story.append(HRFlowable(width="100%", thickness=0.5, color=EARTH))
    story.append(Spacer(1, 0.2*cm))
    story.append(Paragraph(
        f"{_field(designer_name)}  ·  Создано с помощью ВашСад Бот",
        footer_style,
    ))

    doc.build(story)
    return buffer.getvalue()


def generate_guide_pdf(
    designer_name: str = DESIGNER_NAME,
    qualification_line: str = DEFAULT_QUALIFICATION_LINE,
) -> bytes:
    """Генерирует PDF-гайд и возвращает байты.

    Бросает PdfFontError, если шрифт с кириллицей недоступен (см. _ensure_fonts).
    """
    _ensure_fonts()

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=2*cm, rightMargin=2*cm,
        topMargin=2*cm, bottomMargin=2*cm,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "Title", parent=styles["Normal"],
        fontSize=22, textColor=SAGE, alignment=TA_CENTER,
        spaceAfter=4, fontName=PDF_FONT_BOLD,
    )
    subtitle_style = ParagraphStyle(
        "Sub", parent=styles["Normal"],
        fontSize=12, textColor=EARTH, alignment=TA_CENTER,
        spaceAfter=2, fontName=PDF_FONT,
    )
    author_style = ParagraphStyle(
        "Author", parent=styles["Normal"],
        fontSize=10, textColor=DARK, alignment=TA_CENTER,
        spaceAfter=16, fontName=PDF_FONT,
    )
    section_style = ParagraphStyle(
        "Section", parent=styles["Normal"],
        fontSize=14, textColor=SAGE, fontName=PDF_FONT_BOLD,
        spaceBefore=12, spaceAfter=6,
    )
    plant_name_style = ParagraphStyle(
        "PlantName", parent=styles["Normal"],
        fontSize=11, textColor=DARK, fontName=PDF_FONT_BOLD,
    )
    plant_latin_style = ParagraphStyle(
        "PlantLatin", parent=styles["Normal"],
        fontSize=9, textColor=EARTH, fontName=PDF_FONT,
    )
    body_style = ParagraphStyle(
        "Body", parent=styles["Normal"],
        fontSize=9, textColor=DARK, leading=13, fontName=PDF_FONT,
    )
    footer_style = ParagraphStyle(
        "Footer", parent=styles["Normal"],
        fontSize=8, textColor=EARTH, alignment=TA_CENTER, fontName=PDF_FONT,
    )

    story = []

    # ── Обложка ── (эмодзи убираем — DejaVu Sans их не содержит, см. _clean)
    story.append(Spacer(1, 1*cm))
    story.append(Paragraph(_clean("🌿 ВашСад"), title_style))
    story.append(Paragraph("15 растений для природного сада", subtitle_style))
    story.append(Paragraph("Нижегородская и Владимирская области", subtitle_style))
    story.append(Spacer(1, 0.5*cm))
    story.append(HRFlowable(width="100%", thickness=1.5, color=SAGE))
    story.append(Spacer(1, 0.3*cm))
    story.append(Paragraph(f"Составил: {designer_name} · {qualification_line}", author_style))
    story.append(HRFlowable(width="100%", thickness=0.5, color=EARTH))
    story.append(Spacer(1, 0.8*cm))

    # ── Введение ──
    intro = (
        "Природный стиль сада — это гармония с окружающим ландшафтом, "
        "устойчивость к нашему климату и минимум ухода. Растения из этого списка "
        "проверены в условиях средней полосы России: они зимостойки, долговечны "
        "и создают живую экосистему вашего участка."
    )
    story.append(Paragraph(intro, body_style))
    story.append(Spacer(1, 0.6*cm))

    # ── Группировка по категориям ──
    categories_order = ["Деревья", "Кустарники", "Многолетники", "Почвопокровные"]
    by_category: dict = {}
    for p in PLANTS_DATA:
        cat = p[2]
        by_category.setdefault(cat, []).append(p)

    for cat in categories_order:
        plants_in_cat = by_category.get(cat, [])
        if not plants_in_cat:
            continue
        story.append(Paragraph(cat, section_style))

        for (name, latin, _, light, water, zone, desc) in plants_in_cat:
            # Карточка растения как таблица
            tdata = [
                [Paragraph(name, plant_name_style), Paragraph(latin, plant_latin_style)],
                [Paragraph(f"☀ {light}  💧 {water}  ❄ {zone}", body_style), ""],
                [Paragraph(desc, body_style), ""],
            ]
            tbl = Table(tdata, colWidths=[10*cm, 6.5*cm])
            tbl.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), CREAM),
                ("ROWBACKGROUNDS", (0, 0), (-1, -1), [LIGHT, CREAM, CREAM]),
                ("BOX", (0, 0), (-1, -1), 0.5, SAGE),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("SPAN", (0, 2), (-1, 2)),
                ("SPAN", (0, 1), (-1, 1)),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]))
            story.append(tbl)
            story.append(Spacer(1, 0.25*cm))

    # ── Подвал ──
    story.append(Spacer(1, 0.5*cm))
    story.append(HRFlowable(width="100%", thickness=0.5, color=EARTH))
    story.append(Spacer(1, 0.2*cm))
    story.append(Paragraph(
        f"© {designer_name} · ВашСад Бот · Природный ландшафтный дизайн",
        footer_style,
    ))

    doc.build(story)
    return buffer.getvalue()


def generate_clients_pdf(clients_data: list, designer_name: str = DESIGNER_NAME) -> bytes:
    """Генерирует PDF со списком клиентов (уникальные по telegram_id из orders).

    Бросает PdfFontError, если шрифт с кириллицей недоступен (см. _ensure_fonts).
    """
    from datetime import date

    _ensure_fonts()

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=2*cm, rightMargin=2*cm,
        topMargin=2*cm, bottomMargin=2*cm,
    )

    styles = getSampleStyleSheet()

    cover_title_style = ParagraphStyle(
        "ClientsCoverTitle", parent=styles["Normal"],
        fontSize=24, textColor=SAGE, alignment=TA_CENTER,
        fontName=PDF_FONT_BOLD, spaceAfter=6,
    )
    cover_sub_style = ParagraphStyle(
        "ClientsCoverSub", parent=styles["Normal"],
        fontSize=11, textColor=EARTH, alignment=TA_CENTER,
        spaceAfter=4, fontName=PDF_FONT,
    )
    footer_style = ParagraphStyle(
        "ClientsFooter", parent=styles["Normal"],
        fontSize=8, textColor=EARTH, alignment=TA_CENTER,
        spaceBefore=12, fontName=PDF_FONT,
    )
    cell_style = ParagraphStyle(
        "ClientsCell", parent=styles["Normal"],
        fontSize=7, leading=9, fontName=PDF_FONT,
    )

    STATUS_RU = {
        "new": "Новая",
        "in_progress": "В работе",
        "review": "Согласование",
        "done": "Выполнена",
        "canceled": "Отменена",
    }

    story = []

    # ── Обложка ──
    story.append(Spacer(1, 1.5*cm))
    story.append(Paragraph("Клиенты ВашСад", cover_title_style))
    story.append(HRFlowable(width="80%", thickness=2, color=SAGE, hAlign="CENTER"))
    story.append(Spacer(1, 0.4*cm))
    story.append(Paragraph(f"Дата: {date.today().strftime('%d.%m.%Y')}", cover_sub_style))
    story.append(Paragraph(f"Дизайнер: {designer_name}", cover_sub_style))
    story.append(Paragraph(f"Всего клиентов: {len(clients_data)}", cover_sub_style))
    story.append(Spacer(1, 0.8*cm))
    story.append(HRFlowable(width="100%", thickness=0.5, color=EARTH))
    story.append(Spacer(1, 0.5*cm))

    if not clients_data:
        story.append(Paragraph("Клиентов пока нет.", cover_sub_style))
    else:
        headers = ["№", "Имя", "Телефон", "Услуга", "Регион", "Статус", "Дата"]
        data = [headers]
        for i, row in enumerate(clients_data, start=1):
            status_raw = row.get("status") or ""
            status = STATUS_RU.get(status_raw, status_raw) or "—"
            created_at = row.get("created_at")
            date_str = created_at.strftime("%d.%m.%y") if hasattr(created_at, "strftime") else str(created_at or "—")
            data.append([
                str(i),
                Paragraph((row.get("name") or "—")[:18], cell_style),
                Paragraph((row.get("phone") or "—")[:14], cell_style),
                Paragraph((row.get("service_type") or "—")[:22], cell_style),
                Paragraph((row.get("region") or "—")[:16], cell_style),
                status,
                date_str,
            ])

        col_widths = [0.8*cm, 3*cm, 2.5*cm, 4*cm, 2.8*cm, 2.4*cm, 1.8*cm]
        tbl = Table(data, colWidths=col_widths, repeatRows=1)
        tbl.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, 0), SAGE),
            ("TEXTCOLOR",     (0, 0), (-1, 0), white),
            ("FONTNAME",      (0, 0), (-1, 0), PDF_FONT_BOLD),
            ("FONTNAME",      (0, 1), (-1, -1), PDF_FONT),
            ("FONTSIZE",      (0, 0), (-1, 0), 8),
            ("FONTSIZE",      (0, 1), (-1, -1), 7),
            ("ROWBACKGROUNDS",(0, 1), (-1, -1), [white, CREAM]),
            ("GRID",          (0, 0), (-1, -1), 0.3, HexColor("#D4CEC5")),
            ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING",   (0, 0), (-1, -1), 4),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 4),
            ("TOPPADDING",    (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        story.append(tbl)

    # ── Подвал ──
    story.append(Spacer(1, 0.8*cm))
    story.append(HRFlowable(width="100%", thickness=0.5, color=EARTH))
    story.append(Paragraph(
        f"Итого клиентов: {len(clients_data)}  ·  {designer_name}  ·  ВашСад Бот",
        footer_style,
    ))

    doc.build(story)
    return buffer.getvalue()
