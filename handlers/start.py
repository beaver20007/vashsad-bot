"""Хендлер /start — приветствие, главное меню + кнопка Mini App"""
from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import DESIGNER_NAME, BOT_NAME, MINI_APP_URL
from keyboards import main_menu_keyboard, back_to_menu_keyboard
from services.database import get_or_create_user   # ← async версия

router = Router()

WELCOME_TEXT = """🌿 <b>Добро пожаловать в {bot_name}!</b>

Я — AI-помощник {designer_name}, дипломированного ландшафтного дизайнера.

Помогу вам:
🗺 Создать план вашего участка
🌱 Подобрать растения под ваш климат и стиль
📸 Определить болезнь растения по фото
📅 Составить календарь ухода за садом
💬 Ответить на любой вопрос по садоводству

<b>Выберите, с чего начнём 👇</b>"""


def mini_app_keyboard() -> InlineKeyboardMarkup:
    """Кнопка открытия Mini App + основное меню."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="🌿 Открыть ВашСад",
            web_app=WebAppInfo(url=MINI_APP_URL),
        )
    )
    builder.row(
        InlineKeyboardButton(text="🗺 План участка",   callback_data="menu:plan"),
        InlineKeyboardButton(text="🌱 Растения",        callback_data="menu:plants"),
    )
    builder.row(
        InlineKeyboardButton(text="📸 Диагностика",    callback_data="menu:photo"),
        InlineKeyboardButton(text="📋 Заказать",        callback_data="menu:order"),
    )
    builder.row(
        InlineKeyboardButton(text="💰 Прайс",           callback_data="menu:price"),
        InlineKeyboardButton(text="💬 AI-чат",          callback_data="menu:chat"),
    )
    return builder.as_markup()


@router.message(CommandStart())
async def cmd_start(message: Message):
    # Async: сохраняем пользователя в PostgreSQL
    user = await get_or_create_user(
        message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
    )
    name = user.first_name or "друг"
    text = WELCOME_TEXT.format(bot_name=BOT_NAME, designer_name=DESIGNER_NAME)

    await message.answer(
        f"👋 Привет, {name}!\n\n" + text,
        reply_markup=mini_app_keyboard(),
        parse_mode="HTML",
    )


@router.message(Command("help"))
async def cmd_help(message: Message):
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="🌿 Открыть приложение",
            web_app=WebAppInfo(url=MINI_APP_URL),
        )
    )
    builder.row(
        InlineKeyboardButton(text="📋 Заказать проект", callback_data="order:project"),
        InlineKeyboardButton(text="◀️ В меню",          callback_data="menu:main"),
    )
    await message.answer(
        "📖 <b>Что умеет ВашСад Бот:</b>\n\n"
        "🌿 <b>Mini App</b> — полноценное приложение прямо в Telegram\n"
        "🗺 <b>План участка</b> — составлю зонирование и список растений\n"
        "🌱 <b>Подбор растений</b> — подберу под ваш климат и стиль\n"
        "📸 <b>Фото-диагностика</b> — определю болезнь растения\n"
        "💬 <b>AI-консультация</b> — отвечу на любой вопрос по саду\n"
        "💰 <b>Прайс-лист</b> — все услуги и цены\n"
        "📋 <b>Заказать проект</b> — полный дизайн-проект вашего участка\n\n"
        "Откройте приложение или выберите нужное в меню 👇",
        parse_mode="HTML",
        reply_markup=builder.as_markup(),
    )


@router.callback_query(F.data == "menu:main")
async def cb_main_menu(callback: CallbackQuery):
    await callback.message.edit_text(
        WELCOME_TEXT.format(bot_name=BOT_NAME, designer_name=DESIGNER_NAME),
        reply_markup=mini_app_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "cancel")
async def cb_cancel(callback: CallbackQuery):
    await callback.message.edit_text(
        WELCOME_TEXT.format(bot_name=BOT_NAME, designer_name=DESIGNER_NAME),
        reply_markup=mini_app_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(Command("portfolio"))
async def cmd_portfolio(message: Message):
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="🌿 Смотреть портфолио в приложении",
            web_app=WebAppInfo(url=f"{MINI_APP_URL}/portfolio"),
        )
    )
    builder.row(
        InlineKeyboardButton(text="📋 Заказать проект", callback_data="order:project"),
        InlineKeyboardButton(text="◀️ В меню",          callback_data="menu:main"),
    )
    await message.answer(
        "🏡 <b>Портфолио работ</b>\n\n"
        "Все реализованные проекты — в приложении ВашСад.\n"
        "Там удобнее: фото, описания, стили, площади.\n\n"
        "<i>Нажмите кнопку ниже 👇</i>",
        parse_mode="HTML",
        reply_markup=builder.as_markup(),
    )
