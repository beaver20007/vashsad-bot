"""
services/pdf_generator.py
Генерация PDF-гайда «15 растений для природного сада НО» через ReportLab.
"""
import io
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.colors import HexColor, white, black
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT

from config import DESIGNER_NAME

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


def generate_plan_pdf(
    plan_text: str,
    user_name: str,
    area: str,
    style: str,
    designer_name: str = DESIGNER_NAME,
) -> bytes:
    """Генерирует PDF план участка и возвращает байты."""
    from datetime import date

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
        fontSize=28, textColor=SAGE, alignment=TA_CENTER,
        fontName="Helvetica-Bold", spaceAfter=8,
    )
    cover_sub_style = ParagraphStyle(
        "CoverSub", parent=styles["Normal"],
        fontSize=14, textColor=EARTH, alignment=TA_CENTER,
        spaceAfter=4,
    )
    cover_meta_style = ParagraphStyle(
        "CoverMeta", parent=styles["Normal"],
        fontSize=11, textColor=DARK, alignment=TA_CENTER,
        spaceAfter=4,
    )
    h1_style = ParagraphStyle(
        "PlanH1", parent=styles["Normal"],
        fontSize=14, textColor=SAGE, fontName="Helvetica-Bold",
        spaceBefore=14, spaceAfter=6,
    )
    body_style = ParagraphStyle(
        "PlanBody", parent=styles["Normal"],
        fontSize=10, textColor=DARK, leading=15, spaceAfter=4,
    )
    footer_style = ParagraphStyle(
        "PlanFooter", parent=styles["Normal"],
        fontSize=8, textColor=EARTH, alignment=TA_CENTER,
    )

    story = []

    # ── Обложка ──────────────────────────────────────────────────
    story.append(Spacer(1, 2*cm))
    story.append(Paragraph("ПЛАН САДА", cover_title_style))
    story.append(HRFlowable(width="80%", thickness=2, color=SAGE, hAlign="CENTER"))
    story.append(Spacer(1, 0.5*cm))
    story.append(Paragraph(user_name, cover_sub_style))
    story.append(Spacer(1, 0.4*cm))
    story.append(Paragraph(f"Площадь: {area} соток  ·  Стиль: {style}", cover_meta_style))
    story.append(Paragraph(f"Дата: {date.today().strftime('%d.%m.%Y')}", cover_meta_style))
    story.append(Spacer(1, 0.6*cm))
    story.append(Paragraph(f"Дизайнер: {designer_name}", cover_meta_style))
    story.append(Spacer(1, 2*cm))
    story.append(HRFlowable(width="100%", thickness=0.5, color=EARTH))
    story.append(Spacer(1, 0.3*cm))
    story.append(Paragraph(
        "Дипломированный ландшафтный дизайнер · Природный стиль садов · "
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

        # Заголовок: строка начинается с # или это короткая строка ЗАГЛАВНЫМИ
        stripped = line.lstrip("#").strip()
        is_markdown_header = line.startswith("#")
        is_caps_header = (
            line == line.upper()
            and len(line) <= 60
            and any(c.isalpha() for c in line)
        )
        if is_markdown_header or is_caps_header:
            story.append(Paragraph(stripped, h1_style))
        else:
            # Экранируем XML-спецсимволы для ReportLab
            safe = line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            story.append(Paragraph(safe, body_style))

    # ── Подвал ───────────────────────────────────────────────────
    story.append(Spacer(1, 1*cm))
    story.append(HRFlowable(width="100%", thickness=0.5, color=EARTH))
    story.append(Spacer(1, 0.2*cm))
    story.append(Paragraph(
        f"{designer_name}  ·  Создано с помощью ВашСад Бот",
        footer_style,
    ))

    doc.build(story)
    return buffer.getvalue()


def generate_guide_pdf(designer_name: str = DESIGNER_NAME) -> bytes:
    """Генерирует PDF-гайд и возвращает байты."""
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
        spaceAfter=4, fontName="Helvetica-Bold",
    )
    subtitle_style = ParagraphStyle(
        "Sub", parent=styles["Normal"],
        fontSize=12, textColor=EARTH, alignment=TA_CENTER,
        spaceAfter=2,
    )
    author_style = ParagraphStyle(
        "Author", parent=styles["Normal"],
        fontSize=10, textColor=DARK, alignment=TA_CENTER,
        spaceAfter=16,
    )
    section_style = ParagraphStyle(
        "Section", parent=styles["Normal"],
        fontSize=14, textColor=SAGE, fontName="Helvetica-Bold",
        spaceBefore=12, spaceAfter=6,
    )
    plant_name_style = ParagraphStyle(
        "PlantName", parent=styles["Normal"],
        fontSize=11, textColor=DARK, fontName="Helvetica-Bold",
    )
    plant_latin_style = ParagraphStyle(
        "PlantLatin", parent=styles["Normal"],
        fontSize=9, textColor=EARTH, fontName="Helvetica-Oblique",
    )
    body_style = ParagraphStyle(
        "Body", parent=styles["Normal"],
        fontSize=9, textColor=DARK, leading=13,
    )
    footer_style = ParagraphStyle(
        "Footer", parent=styles["Normal"],
        fontSize=8, textColor=EARTH, alignment=TA_CENTER,
    )

    story = []

    # ── Обложка ──
    story.append(Spacer(1, 1*cm))
    story.append(Paragraph("🌿 ВашСад", title_style))
    story.append(Paragraph("15 растений для природного сада", subtitle_style))
    story.append(Paragraph("Нижегородская и Владимирская области", subtitle_style))
    story.append(Spacer(1, 0.5*cm))
    story.append(HRFlowable(width="100%", thickness=1.5, color=SAGE))
    story.append(Spacer(1, 0.3*cm))
    story.append(Paragraph(f"Составил: {designer_name} · Дипломированный ландшафтный дизайнер", author_style))
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
            header_row = [
                [Paragraph(name, plant_name_style),
                 Paragraph(latin, plant_latin_style)],
            ]
            props_row = [[
                Paragraph(f"☀ {light}  💧 {water}  ❄ {zone}", body_style),
                "",
            ]]
            desc_row = [[Paragraph(desc, body_style), ""]]

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
    """Генерирует PDF со списком клиентов (уникальные по telegram_id из orders)."""
    from datetime import date

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
        fontName="Helvetica-Bold", spaceAfter=6,
    )
    cover_sub_style = ParagraphStyle(
        "ClientsCoverSub", parent=styles["Normal"],
        fontSize=11, textColor=EARTH, alignment=TA_CENTER,
        spaceAfter=4,
    )
    footer_style = ParagraphStyle(
        "ClientsFooter", parent=styles["Normal"],
        fontSize=8, textColor=EARTH, alignment=TA_CENTER,
        spaceBefore=12,
    )
    cell_style = ParagraphStyle(
        "ClientsCell", parent=styles["Normal"],
        fontSize=7, leading=9,
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
        story.append(Paragraph("Клиентов пока нет.", styles["Normal"]))
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
            ("FONTNAME",      (0, 0), (-1, 0), "Helvetica-Bold"),
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
