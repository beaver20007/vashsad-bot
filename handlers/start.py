"""Хендлер /start — приветствие и главное меню"""
from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery

from config import DESIGNER_NAME, BOT_NAME
from keyboards import main_menu_keyboard, back_to_menu_keyboard
from services.storage import get_or_create_user

router = Router()

WELCOME_TEXT = """🌿 <b>Добро пожаловать в {bot_name}!</b>

Я — AI-помощник {designer_name}, дипломированного ландшафтного дизайнера.

Помогу вам:
🗺 Создать план вашего участка
🌱 Подобрать растения под ваш климат и стиль
📸 Определить болезнь растения по фото
📅 Составить календарь ухода за садом
💬 Ответить на любой вопрос по садоводству

А если нужен профессиональный проект — просто напишите, рассчитаем стоимость!

<b>Выберите, с чего начнём 👇</b>"""


@router.message(CommandStart())
async def cmd_start(message: Message):
    user = get_or_create_user(
        message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
    )
    name = user.first_name or "друг"
    text = WELCOME_TEXT.format(bot_name=BOT_NAME, designer_name=DESIGNER_NAME)
    await message.answer(
        f"👋 Привет, {name}!\n\n" + text,
        reply_markup=main_menu_keyboard(),
        parse_mode="HTML",
    )


@router.message(Command("help"))
async def cmd_help(message: Message):
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📋 Заказать проект", callback_data="order:project"),
        InlineKeyboardButton(text="◀️ В меню", callback_data="menu:main"),
    )
    await message.answer(
        "📖 <b>Что умеет ВашСад Бот:</b>\n\n"
        "🗺 <b>План участка</b> — составлю зонирование и список растений\n"
        "🌱 <b>Подбор растений</b> — подберу под ваш климат и стиль\n"
        "📸 <b>Фото-диагностика</b> — определю болезнь растения\n"
        "💬 <b>AI-консультация</b> — отвечу на любой вопрос по саду\n"
        "💰 <b>Прайс-лист</b> — все услуги и цены\n"
        "📋 <b>Заказать проект</b> — полный дизайн-проект вашего участка\n\n"
        "Выберите нужное в меню или нажмите кнопку ниже 👇",
        parse_mode="HTML",
        reply_markup=builder.as_markup(),
    )


@router.callback_query(F.data == "menu:main")
async def cb_main_menu(callback: CallbackQuery):
    await callback.message.edit_text(
        WELCOME_TEXT.format(bot_name=BOT_NAME, designer_name=DESIGNER_NAME),
        reply_markup=main_menu_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "cancel")
async def cb_cancel(callback: CallbackQuery):
    await callback.message.edit_text(
        WELCOME_TEXT.format(bot_name=BOT_NAME, designer_name=DESIGNER_NAME),
        reply_markup=main_menu_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(Command("portfolio"))
async def cmd_portfolio(message: Message):
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📋 Заказать проект", callback_data="order:project"),
        InlineKeyboardButton(text="◀️ В меню", callback_data="menu:main"),
    )
    await message.answer(
        "🏡 <b>Портфолио работ</b>\n\n"
        "Примеры реализованных проектов:\n\n"
        "📍 Участок 12 соток, Подмосковье — английский сад\n"
        "📍 Дача 6 соток, Ленобласть — огород + цветники\n"
        "📍 Коттедж 25 соток, Краснодар — средиземноморский стиль\n\n"
        "<i>Хотите такой же результат? Нажмите «Заказать проект» 👇</i>",
        parse_mode="HTML",
        reply_markup=builder.as_markup(),
    )
