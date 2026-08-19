"""Хендлер заказа — редирект в Mini App (F1.2/F3.2)"""
import logging
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, WebAppInfo
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import MINI_APP_URL

router = Router()
log = logging.getLogger(__name__)


# ── Заказ услуг — редирект в Mini App (F3.2, решение F1.2 от 05.08.2026) ──
# Старая текстовая FSM-анкета (выбор услуги/бриф индивидуального проекта,
# сбор телефона/email/геолокации, обещание «свяжется в течение 24 часов»)
# была нерабочей мёртвой веткой с PR #5 (18.08.2026) — ни одна кнопка или
# команда её больше не запускала. Удалена треком F3.5 (та же дата); полный
# текст сохранён в git-истории этого файла до этого коммита. Единственный
# путь заказа — Mini App.

ORDER_REDIRECT_TEXT = (
    "📋 <b>Заказать услугу</b>\n\n"
    "Оформление заявок — в приложении ВашСад: там же можно выбрать стиль "
    "сада и услугу.\n\n"
    "Нажмите кнопку ниже 👇"
)


def order_miniapp_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="🌿 Открыть ВашСад",
            web_app=WebAppInfo(url=f"{MINI_APP_URL}?screen=order"),
        )
    )
    return builder.as_markup()


@router.message(Command("order"))
async def cmd_order(message: Message):
    await message.answer(
        ORDER_REDIRECT_TEXT,
        parse_mode="HTML", reply_markup=order_miniapp_keyboard(),
    )


@router.callback_query(F.data == "menu:order")
async def cb_order(callback: CallbackQuery):
    await callback.message.edit_text(
        ORDER_REDIRECT_TEXT,
        parse_mode="HTML", reply_markup=order_miniapp_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "order:start")
async def cb_order_start(callback: CallbackQuery):
    await callback.message.edit_text(
        ORDER_REDIRECT_TEXT,
        parse_mode="HTML", reply_markup=order_miniapp_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "order:project")
async def cb_order_project(callback: CallbackQuery):
    await callback.message.edit_text(
        ORDER_REDIRECT_TEXT,
        parse_mode="HTML", reply_markup=order_miniapp_keyboard(),
    )
    await callback.answer()
