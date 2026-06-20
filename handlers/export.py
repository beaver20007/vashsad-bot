"""Фаза 2: Экспорт PDF — все заявки за период для дизайнера"""
import csv
import io
import logging
import os
from datetime import datetime, timedelta
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import (
    Message, BufferedInputFile, InlineKeyboardButton,
    InlineKeyboardMarkup, CallbackQuery,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import DESIGNER_TELEGRAM_ID
from services.database import _pool

router = Router()
log = logging.getLogger(__name__)

PERIODS = [
    ("7 дней",  7,  "week"),
    ("30 дней", 30, "month"),
    ("90 дней", 90, "quarter"),
    ("Всё время", 9999, "all"),
]


@router.message(Command("export"))
async def cmd_export(message: Message):
    if message.from_user.id != DESIGNER_TELEGRAM_ID:
        return
    builder = InlineKeyboardBuilder()
    for label, _, key in PERIODS:
        builder.row(InlineKeyboardButton(text=label, callback_data=f"export:{key}"))
    await message.answer(
        "📄 <b>Экспорт заявок</b>\n\nВыберите период:",
        parse_mode="HTML",
        reply_markup=builder.as_markup(),
    )


@router.callback_query(F.data.startswith("export:"))
async def cb_export(callback: CallbackQuery):
    if callback.from_user.id != DESIGNER_TELEGRAM_ID:
        await callback.answer("Нет доступа", show_alert=True)
        return

    key = callback.data.split(":")[1]
    days = next((d for _, d, k in PERIODS if k == key), 30)
    label = next((l for l, _, k in PERIODS if k == key), "период")

    await callback.answer("Генерирую PDF…")

    since = datetime.now() - timedelta(days=days) if days < 9999 else datetime(2000, 1, 1)

    async with _pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT o.id, o.service_name, o.status, o.created_at,
                      o.phone, o.email, o.wishes, o.service_price,
                      u.first_name, u.username, u.telegram_id
               FROM orders o
               LEFT JOIN users u ON u.telegram_id = o.telegram_id
               WHERE o.created_at >= $1
               ORDER BY o.created_at DESC""",
            since,
        )

    pdf_bytes = _build_pdf(rows, label)
    filename = f"ВашСад_заявки_{label.replace(' ', '_')}_{datetime.now().strftime('%d%m%Y')}.pdf"

    await callback.message.answer_document(
        document=BufferedInputFile(pdf_bytes, filename=filename),
        caption=f"📄 Заявки за: <b>{label}</b>\nВсего: {len(rows)} шт.",
        parse_mode="HTML",
    )


@router.message(Command("favorites_pdf"))
async def cmd_favorites_pdf(message: Message):
    telegram_id = message.from_user.id
    await message.answer("🌿 Генерирую PDF с вашими растениями…")

    async with _pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT plant_name, latin_name, care_tips, added_at
               FROM user_plants
               WHERE telegram_id = $1
               ORDER BY added_at DESC""",
            telegram_id,
        )

    if not rows:
        await message.answer("У вас пока нет сохранённых растений. Добавьте их через раздел «Подбор растений».")
        return

    pdf_bytes = _build_favorites_pdf(rows)
    filename = f"ВашСад_растения_{datetime.now().strftime('%d%m%Y')}.pdf"

    await message.answer_document(
        document=BufferedInputFile(pdf_bytes, filename=filename),
        caption=f"🌿 <b>Мои растения — ВашСад</b>\nВсего: {len(rows)} шт.",
        parse_mode="HTML",
    )


@router.message(Command("export_csv"))
async def cmd_export_csv(message: Message):
    designer_id = int(os.getenv("DESIGNER_TELEGRAM_ID", "0"))
    if message.from_user.id != designer_id:
        return

    await message.answer("📊 Выберите период:", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="7 дней", callback_data="csv:7")],
        [InlineKeyboardButton(text="30 дней", callback_data="csv:30")],
        [InlineKeyboardButton(text="90 дней", callback_data="csv:90")],
        [InlineKeyboardButton(text="Все заявки", callback_data="csv:all")],
    ]))


@router.callback_query(F.data.startswith("csv:"))
async def cb_csv(callback: CallbackQuery):
    designer_id = int(os.getenv("DESIGNER_TELEGRAM_ID", "0"))
    if callback.from_user.id != designer_id:
        await callback.answer()
        return

    period = callback.data.split(":")[1]
    await callback.answer("Генерирую CSV...")

    async with _pool.acquire() as conn:
        if period == "all":
            rows = await conn.fetch(
                "SELECT id, telegram_id, service_name AS service_type, status, created_at, phone AS contact_phone, service_price AS budget_range "
                "FROM orders ORDER BY created_at DESC"
            )
            period_label = "Все заявки"
        else:
            days = int(period)
            rows = await conn.fetch(
                "SELECT id, telegram_id, service_name AS service_type, status, created_at, phone AS contact_phone, service_price AS budget_range "
                "FROM orders WHERE created_at > NOW() - INTERVAL '1 day' * $1 ORDER BY created_at DESC",
                days,
            )
            period_label = f"За {days} дней"

    output = io.StringIO()
    writer = csv.writer(output, delimiter=';')
    writer.writerow(["ID", "Telegram ID", "Услуга", "Статус", "Дата", "Телефон", "Бюджет"])
    for row in rows:
        writer.writerow([
            row["id"],
            row["telegram_id"],
            row.get("service_type", ""),
            row.get("status", ""),
            row["created_at"].strftime("%Y-%m-%d %H:%M") if row.get("created_at") else "",
            row.get("contact_phone", ""),
            row.get("budget_range", ""),
        ])

    csv_bytes = output.getvalue().encode("utf-8-sig")  # BOM for Excel
    file = BufferedInputFile(csv_bytes, filename=f"orders_{period_label}.csv")

    await callback.message.answer_document(
        file,
        caption=f"📊 {period_label}: {len(rows)} заявок",
    )


def _build_favorites_pdf(rows) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import cm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            leftMargin=2*cm, rightMargin=2*cm,
                            topMargin=2*cm, bottomMargin=2.5*cm)

    SAGE  = colors.HexColor("#4A6B50")
    CREAM = colors.HexColor("#F9F7F3")
    EARTH = colors.HexColor("#8B6F47")

    styles = getSampleStyleSheet()
    title_style  = ParagraphStyle("fav_title", parent=styles["Normal"],
                                  fontSize=20, textColor=SAGE, spaceAfter=4, fontName="Helvetica-Bold")
    sub_style    = ParagraphStyle("fav_sub", parent=styles["Normal"],
                                  fontSize=10, textColor=colors.grey, spaceAfter=16)
    plant_name_s = ParagraphStyle("plant_name", parent=styles["Normal"],
                                  fontSize=13, textColor=SAGE, fontName="Helvetica-Bold", spaceAfter=2)
    latin_style  = ParagraphStyle("latin", parent=styles["Normal"],
                                  fontSize=10, textColor=EARTH, spaceAfter=4, fontName="Helvetica-Oblique")
    care_style   = ParagraphStyle("care", parent=styles["Normal"],
                                  fontSize=9, textColor=colors.HexColor("#333333"), leading=13, spaceAfter=8)
    footer_style = ParagraphStyle("footer", parent=styles["Normal"],
                                  fontSize=8, textColor=colors.grey, spaceBefore=20)

    elems = []
    elems.append(Paragraph("Мои растения — ВашСад", title_style))
    elems.append(Paragraph(
        f"Сохранено: {len(rows)} растений  ·  Дата: {datetime.now().strftime('%d.%m.%Y')}",
        sub_style,
    ))
    elems.append(HRFlowable(width="100%", thickness=1, color=SAGE, spaceAfter=12))

    for r in rows:
        plant_name = r["plant_name"] or "Без названия"
        latin_name = r["latin_name"] or ""
        care_tips  = r["care_tips"] or ""
        added_at   = r["added_at"]

        elems.append(Paragraph(plant_name, plant_name_s))
        if latin_name:
            elems.append(Paragraph(latin_name, latin_style))
        if care_tips:
            elems.append(Paragraph(f"Уход: {care_tips}", care_style))
        if added_at:
            elems.append(Paragraph(
                f"Добавлено: {added_at.strftime('%d.%m.%Y') if hasattr(added_at, 'strftime') else str(added_at)}",
                ParagraphStyle("date", parent=styles["Normal"], fontSize=8, textColor=colors.grey, spaceAfter=6),
            ))
        elems.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#D4CEC5"), spaceAfter=10))

    elems.append(Spacer(1, 0.5*cm))
    elems.append(Paragraph(
        "ВашСад · Дипломированный ландшафтный дизайнер · Нижегородская и Владимирская области · @vashsad_bot",
        footer_style,
    ))

    doc.build(elems)
    return buf.getvalue()


def _build_pdf(rows, period_label: str) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import cm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    import os

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            leftMargin=2*cm, rightMargin=2*cm,
                            topMargin=2*cm, bottomMargin=2*cm)

    SAGE  = colors.HexColor("#4A6B50")
    CREAM = colors.HexColor("#F9F7F3")
    EARTH = colors.HexColor("#8B6F47")

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("title", parent=styles["Normal"],
                                 fontSize=18, textColor=SAGE, spaceAfter=6, fontName="Helvetica-Bold")
    sub_style   = ParagraphStyle("sub", parent=styles["Normal"],
                                 fontSize=10, textColor=colors.grey, spaceAfter=12)
    cell_style  = ParagraphStyle("cell", parent=styles["Normal"], fontSize=8, leading=10)

    STATUS_RU = {
        "new": "Новая", "in_progress": "В работе",
        "review": "Согласование", "done": "Выполнена", "canceled": "Отменена",
    }

    elems = []
    elems.append(Paragraph("ВашСад — Отчёт по заявкам", title_style))
    elems.append(Paragraph(f"Период: {period_label}  ·  Всего заявок: {len(rows)}  ·  Дата: {datetime.now().strftime('%d.%m.%Y')}", sub_style))

    if not rows:
        elems.append(Paragraph("Заявок за этот период нет.", styles["Normal"]))
        doc.build(elems)
        return buf.getvalue()

    revenue = sum(r["service_price"] or 0 for r in rows)
    elems.append(Paragraph(f"Выручка (оценка): {revenue:,} ₽", sub_style))
    elems.append(Spacer(1, 0.3*cm))

    headers = ["#", "Дата", "Клиент", "Услуга", "Статус", "Телефон", "Сумма"]
    data = [headers]
    for r in rows:
        data.append([
            str(r["id"]),
            r["created_at"].strftime("%d.%m.%y"),
            (r["first_name"] or "—")[:12],
            Paragraph((r["service_name"] or "—")[:30], cell_style),
            STATUS_RU.get(r["status"] or "", r["status"] or "—"),
            r["phone"] or "—",
            f"{r['service_price']:,} ₽" if r["service_price"] else "—",
        ])

    col_widths = [1*cm, 1.8*cm, 2.5*cm, 5.5*cm, 2.5*cm, 2.8*cm, 2*cm]
    tbl = Table(data, colWidths=col_widths, repeatRows=1)
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), SAGE),
        ("TEXTCOLOR",  (0,0), (-1,0), colors.white),
        ("FONTNAME",   (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE",   (0,0), (-1,0), 8),
        ("FONTSIZE",   (0,1), (-1,-1), 7),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, CREAM]),
        ("GRID",       (0,0), (-1,-1), 0.3, colors.HexColor("#D4CEC5")),
        ("VALIGN",     (0,0), (-1,-1), "MIDDLE"),
        ("LEFTPADDING",  (0,0), (-1,-1), 4),
        ("RIGHTPADDING", (0,0), (-1,-1), 4),
        ("TOPPADDING",   (0,0), (-1,-1), 3),
        ("BOTTOMPADDING",(0,0), (-1,-1), 3),
    ]))
    elems.append(tbl)
    doc.build(elems)
    return buf.getvalue()
