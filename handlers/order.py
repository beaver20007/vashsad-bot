"""Хендлер заказа услуг и проектов"""
import logging
import os
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton

from config import SERVICES, DESIGNER_TELEGRAM_ID, DESIGNER_NAME
from keyboards import (
    services_keyboard, order_confirm_keyboard,
    back_to_menu_keyboard, cancel_keyboard
)
from services.email_service import notify_email_new_order, notify_email_new_project

router = Router()
log = logging.getLogger(__name__)

DESIGNER_TELEGRAM_ID_2 = int(os.getenv("DESIGNER_TELEGRAM_ID_2", "0"))


async def notify_all(bot, msg_text: str):
    for chat_id in [DESIGNER_TELEGRAM_ID, DESIGNER_TELEGRAM_ID_2]:
        if chat_id:
            try:
                await bot.send_message(chat_id, msg_text, parse_mode="HTML")
            except Exception as e:
                log.error(f"Не удалось уведомить {chat_id}: {e}")


def normalize_phone(text: str) -> str:
    digits = "".join(c for c in text if c.isdigit())
    if len(digits) == 11 and digits.startswith("8"):
        return "+7" + digits[1:]
    elif len(digits) == 11 and digits.startswith("7"):
        return "+" + digits
    elif len(digits) == 10 and digits.startswith("9"):
        return "+7" + digits
    elif len(digits) >= 10:
        return "+" + digits
    return text


def skip_inline_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="➡️ Пропустить", callback_data="skip_extra"),
        InlineKeyboardButton(text="❌ Отмена", callback_data="cancel"),
    )
    return builder.as_markup()


class OrderForm(StatesGroup):
    contact_phone  = State()
    contact_extra  = State()
    brief_area     = State()
    brief_existing = State()
    brief_style    = State()
    brief_wishes   = State()
    brief_phone    = State()
    brief_extra    = State()


STYLE_KB_TEXT = {
    "english":  "Английский (романтичный)",
    "modern":   "Современный (минимализм)",
    "russian":  "Русский (природный)",
    "country":  "Кантри / прованс",
    "japanese": "Японский (дзен)",
    "unknown":  "Пока не знаю",
}

PHONE_PROMPT = (
    "📱 <b>Телефон</b>\n\n"
    "Введите номер телефона:\n\n"
    "<code>89161234567</code>  →  <code>+79161234567</code>\n"
    "<code>9161234567</code>   →  <code>+79161234567</code>\n"
    "<code>+79161234567</code> →  оставим как есть"
)

EMAIL_PROMPT = (
    "📧 <b>Email</b>\n\n"
    "Введите ваш email для отправки материалов.\n\n"
    "Или нажмите «Пропустить»."
)


# ══════════════════════════════════════════════════════════════
#  СТАРТОВЫЕ УСЛУГИ
# ══════════════════════════════════════════════════════════════

@router.message(Command("order"))
async def cmd_order(message: Message):
    await message.answer(
        "📋 <b>Заказать услугу</b>\n\n"
        "Выберите нужную услугу или закажите индивидуальный проект:",
        parse_mode="HTML",
        reply_markup=services_keyboard(),
    )


@router.callback_query(F.data == "menu:order")
async def cb_order(callback: CallbackQuery):
    await callback.message.edit_text(
        "📋 <b>Заказать услугу</b>\n\n"
        "Выберите нужную услугу или закажите индивидуальный проект:",
        parse_mode="HTML",
        reply_markup=services_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "order:start")
async def cb_order_start(callback: CallbackQuery):
    await callback.message.edit_text(
        "📋 <b>Стартовые услуги</b>\n\nВыберите услугу:",
        parse_mode="HTML",
        reply_markup=services_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("service:"))
async def cb_service_detail(callback: CallbackQuery):
    key = callback.data.split(":")[1]
    svc = SERVICES.get(key)
    if not svc:
        await callback.answer("Услуга не найдена")
        return
    price_str = f"{svc['price']:,} ₽".replace(",", " ")
    await callback.message.edit_text(
        f"📋 <b>{svc['name']}</b>\n\n"
        f"💰 Стоимость: <b>{price_str}</b>\n"
        f"⏱ Срок: {svc['duration']}\n\n"
        f"📝 {svc['description']}\n\n"
        f"Нажмите «Подтвердить заказ» и мы свяжемся с вами в течение 24 часов.",
        parse_mode="HTML",
        reply_markup=order_confirm_keyboard(key),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("confirm:"))
async def cb_confirm_service(callback: CallbackQuery, state: FSMContext):
    key = callback.data.split(":")[1]
    svc = SERVICES.get(key)
    if not svc:
        await callback.answer("Услуга не найдена")
        return
    await state.update_data(service_key=key, service_name=svc["name"], service_price=svc["price"])
    await state.set_state(OrderForm.contact_phone)

    await callback.message.edit_text(
        f"✅ Вы выбрали: <b>{svc['name']}</b>\n\n"
        f"{PHONE_PROMPT}",
        parse_mode="HTML",
        reply_markup=cancel_keyboard(),
    )
    await callback.answer()


@router.message(OrderForm.contact_phone)
async def contact_phone(message: Message, state: FSMContext):
    phone = normalize_phone(message.text or "")
    await state.update_data(phone=phone)
    await state.set_state(OrderForm.contact_extra)
    try:
        await message.delete()
    except Exception:
        pass

    await message.answer(
        f"✅ Телефон: <code>{phone}</code>\n\n{EMAIL_PROMPT}",
        parse_mode="HTML",
        reply_markup=skip_inline_keyboard(),
    )


@router.callback_query(F.data == "skip_extra", OrderForm.contact_extra)
async def skip_contact_extra(callback: CallbackQuery, state: FSMContext):
    await _finish_contact(callback.message, state, email="не указан",
                          user=callback.from_user, edit=True)
    await callback.answer()


@router.message(OrderForm.contact_extra)
async def contact_extra(message: Message, state: FSMContext):
    email = message.text or "не указан"
    try:
        await message.delete()
    except Exception:
        pass
    await _finish_contact(message, state, email=email, user=message.from_user)


async def _finish_contact(message, state, email, user, edit=False):
    data = await state.get_data()
    await state.clear()

    svc_name  = data.get("service_name", "Услуга")
    svc_price = data.get("service_price", 0)
    price_str = f"{svc_price:,} ₽".replace(",", " ")
    phone     = data.get("phone", "не указан")
    user_info = f"{user.full_name} (@{user.username or 'нет'})"
    dt        = message.date.strftime("%d.%m.%Y %H:%M")

    designer_msg = (
        f"🌿 <b>НОВАЯ ЗАЯВКА — ВашСад Бот</b>\n\n"
        f"👤 Клиент: {user_info}\n"
        f"📋 Услуга: {svc_name}\n"
        f"💰 Сумма: {price_str}\n"
        f"📱 Телефон: {phone}\n"
        f"📧 Email: {email}\n\n"
        f"⏰ {dt}"
    )
    # Telegram + Email параллельно
    import asyncio
    await asyncio.gather(
        notify_all(message.bot, designer_msg),
        notify_email_new_order(user_info, svc_name, price_str, phone, email, dt),
    )

    result_text = (
        f"✅ <b>Заявка принята!</b>\n\n"
        f"Вы заказали: <b>{svc_name}</b> ({price_str})\n\n"
        f"📱 Телефон: <code>{phone}</code>\n"
        f"📧 Email: {email}\n\n"
        f"<b>{DESIGNER_NAME}</b> свяжется с вами в течение 24 часов.\n\n"
        f"Спасибо, что выбрали ВашСад! 🌿"
    )

    if edit:
        await message.edit_text(result_text, parse_mode="HTML",
                                reply_markup=back_to_menu_keyboard())
    else:
        await message.answer(result_text, parse_mode="HTML",
                             reply_markup=back_to_menu_keyboard())


# ══════════════════════════════════════════════════════════════
#  БРИФ ДЛЯ ИНДИВИДУАЛЬНОГО ПРОЕКТА
# ══════════════════════════════════════════════════════════════

@router.callback_query(F.data == "order:project")
async def cb_order_project(callback: CallbackQuery, state: FSMContext):
    await state.set_state(OrderForm.brief_area)
    await callback.message.edit_text(
        "🏡 <b>Индивидуальный ландшафтный проект</b>\n\n"
        "Заполним небольшой бриф — 4 вопроса + контакты.\n\n"
        "📐 <b>Вопрос 1/4:</b> Какова площадь вашего участка?\n"
        "<i>Например: 10 соток, 15 соток, 0.5 га</i>",
        parse_mode="HTML",
        reply_markup=cancel_keyboard(),
    )
    await callback.answer()


@router.message(OrderForm.brief_area)
async def brief_area(message: Message, state: FSMContext):
    await state.update_data(area=message.text)
    await state.set_state(OrderForm.brief_existing)
    try:
        await message.delete()
    except Exception:
        pass

    builder = InlineKeyboardBuilder()
    for text, data in [
        ("🌱 Пустой участок",   "Пустой участок"),
        ("🏠 Дом уже есть",     "Дом есть"),
        ("🌳 Старый сад",        "Старый сад"),
        ("🏗 Есть хозпостройки", "Хозпостройки"),
    ]:
        builder.row(InlineKeyboardButton(text=text, callback_data=f"existing:{data}"))
    builder.row(InlineKeyboardButton(text="◀️ Отмена", callback_data="cancel"))

    await message.answer(
        "🏠 <b>Вопрос 2/4:</b> Что сейчас есть на участке?",
        parse_mode="HTML",
        reply_markup=builder.as_markup(),
    )


@router.callback_query(F.data.startswith("existing:"), OrderForm.brief_existing)
async def brief_existing(callback: CallbackQuery, state: FSMContext):
    await state.update_data(existing=callback.data.split(":", 1)[1])
    await state.set_state(OrderForm.brief_style)

    builder = InlineKeyboardBuilder()
    for code, name in STYLE_KB_TEXT.items():
        builder.row(InlineKeyboardButton(text=name, callback_data=f"style:{code}"))
    builder.row(InlineKeyboardButton(text="◀️ Отмена", callback_data="cancel"))

    await callback.message.edit_text(
        "🎨 <b>Вопрос 3/4:</b> Какой стиль сада вам нравится?",
        parse_mode="HTML",
        reply_markup=builder.as_markup(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("style:"), OrderForm.brief_style)
async def brief_style(callback: CallbackQuery, state: FSMContext):
    code = callback.data.split(":")[1]
    await state.update_data(style=STYLE_KB_TEXT.get(code, code))
    await state.set_state(OrderForm.brief_wishes)

    await callback.message.edit_text(
        "💬 <b>Вопрос 4/4:</b> Что самое важное для вас в саду?\n\n"
        "<i>Напишите текстом: газон, цветники, зона отдыха, "
        "детская площадка, огород и т.д.</i>",
        parse_mode="HTML",
        reply_markup=cancel_keyboard(),
    )
    await callback.answer()


@router.message(OrderForm.brief_wishes)
async def brief_wishes(message: Message, state: FSMContext):
    await state.update_data(wishes=message.text)
    await state.set_state(OrderForm.brief_phone)
    try:
        await message.delete()
    except Exception:
        pass

    await message.answer(
        f"📱 <b>Контакты 1/2 — Телефон</b>\n\n{PHONE_PROMPT}",
        parse_mode="HTML",
        reply_markup=cancel_keyboard(),
    )


@router.message(OrderForm.brief_phone)
async def brief_phone(message: Message, state: FSMContext):
    phone = normalize_phone(message.text or "")
    await state.update_data(phone=phone)
    await state.set_state(OrderForm.brief_extra)
    try:
        await message.delete()
    except Exception:
        pass

    await message.answer(
        f"✅ Телефон: <code>{phone}</code>\n\n"
        f"📧 <b>Контакты 2/2 — Email</b>\n\n{EMAIL_PROMPT}",
        parse_mode="HTML",
        reply_markup=skip_inline_keyboard(),
    )


@router.callback_query(F.data == "skip_extra", OrderForm.brief_extra)
async def skip_brief_extra(callback: CallbackQuery, state: FSMContext):
    await _finish_brief(callback.message, state, email="не указан",
                        user=callback.from_user, edit=True)
    await callback.answer()


@router.message(OrderForm.brief_extra)
async def brief_extra(message: Message, state: FSMContext):
    email = message.text or "не указан"
    try:
        await message.delete()
    except Exception:
        pass
    await _finish_brief(message, state, email=email, user=message.from_user)


async def _finish_brief(message, state, email, user, edit=False):
    data = await state.get_data()
    await state.clear()

    user_info = f"{user.full_name} (@{user.username or 'нет'})"
    phone     = data.get("phone", "не указан")
    dt        = message.date.strftime("%d.%m.%Y %H:%M")

    designer_msg = (
        f"🌿 <b>НОВАЯ ЗАЯВКА НА ПРОЕКТ — ВашСад Бот</b>\n\n"
        f"👤 Клиент: {user_info}\n"
        f"📐 Площадь: {data.get('area', '?')}\n"
        f"🏠 Участок: {data.get('existing', '?')}\n"
        f"🎨 Стиль: {data.get('style', '?')}\n"
        f"💬 Пожелания: {data.get('wishes', '?')}\n"
        f"📱 Телефон: {phone}\n"
        f"📧 Email: {email}\n\n"
        f"⏰ {dt}"
    )

    import asyncio
    await asyncio.gather(
        notify_all(message.bot, designer_msg),
        notify_email_new_project(
            user_info, data.get("area", "?"), data.get("existing", "?"),
            data.get("style", "?"), data.get("wishes", "?"), phone, email, dt
        ),
    )

    result_text = (
        f"✅ <b>Бриф отправлен!</b>\n\n"
        f"📱 Телефон: <code>{phone}</code>\n"
        f"📧 Email: {email}\n\n"
        f"<b>{DESIGNER_NAME}</b> свяжется с вами в течение 24 часов "
        f"и рассчитает стоимость проекта.\n\n"
        f"Спасибо, что выбрали ВашСад! 🌿"
    )

    if edit:
        await message.edit_text(result_text, parse_mode="HTML",
                                reply_markup=back_to_menu_keyboard())
    else:
        await message.answer(result_text, parse_mode="HTML",
                             reply_markup=back_to_menu_keyboard())
