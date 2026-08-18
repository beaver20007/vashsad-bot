"""Хендлер /start — приветствие, главное меню + кнопка Mini App"""
import os
from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo,
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import (
    BOT_NAME, DESIGNER_NAME, DESIGNER_NAME_GEN, MINI_APP_URL, WELCOME_IMAGE_URL,
    FREE_CHAT_LIMIT, FREE_PHOTO_LIMIT, FREE_PLANTS_LIMIT,
)
from keyboards import main_menu_keyboard, back_to_menu_keyboard
from services.database import get_or_create_user, insert_analytics_event
from services.i18n import t

SCREEN_LINKS = {
    'screen_garden': ('🏡 Мой сад', 'garden'),
    'screen_order': ('📋 Заказать услугу', 'order'),
    'screen_plants': ('🌺 Каталог растений', 'plants'),
    'screen_profile': ('👤 Профиль', 'profile'),
    'screen_chat': ('💬 AI-чат', 'chat'),
    'screen_diary': ('📓 Дневник сада', 'diary'),
    'screen_nurseries': ('🗺 Питомники', 'nurseries'),
}

router = Router()

MAIN_KEYBOARD = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🌺 Растения"), KeyboardButton(text="📸 Диагностика")],
        [KeyboardButton(text="📋 Заказать услугу"), KeyboardButton(text="💬 AI-чат")],
        [KeyboardButton(text="📅 Консультация"), KeyboardButton(text="👤 Профиль")],
    ],
    resize_keyboard=True,
    input_field_placeholder="Выберите действие или напишите вопрос...",
)

# ── A/B тест приветствия (фаза 3) ───────────────────────────
_AB_VARIANT_A = """🌿 <b>Добро пожаловать в {bot_name}!</b>

Я — AI-помощник {designer_name}, дипломированного ландшафтного дизайнера.

Помогу вам:
🗺 Создать план вашего участка
🌱 Подобрать растения под ваш климат и стиль
📸 Определить болезнь растения по фото
📅 Составить календарь ухода за садом
💬 Ответить на любой вопрос по садоводству

<b>Выберите, с чего начнём 👇</b>"""

_AB_VARIANT_B = """🌿 <b>{bot_name} — сад вашей мечты</b>

{designer_name} помогает создавать природные сады в Нижегородской и Владимирской областях.

Что я умею:
✨ Составить план участка с нуля
🌱 Подобрать растения под ваш климат
📸 Диагностировать болезни по фото
💡 Ответить на любой вопрос о саде

🎁 <b>10 бесплатных AI-консультаций</b> для новых пользователей!

<b>Открывайте приложение и начнём 👇</b>"""

_AB_STATS: dict[str, int] = {"A": 0, "B": 0, "A_orders": 0, "B_orders": 0}


def _pick_ab_variant(telegram_id: int) -> tuple[str, str]:
    """Детерминированный выбор варианта по telegram_id (чётный = A, нечётный = B)."""
    variant = "A" if telegram_id % 2 == 0 else "B"
    _AB_STATS[variant] += 1
    return variant, (_AB_VARIANT_A if variant == "A" else _AB_VARIANT_B)


WELCOME_TEXT = _AB_VARIANT_A  # fallback для cb_main_menu


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
async def cmd_start(message: Message, state: FSMContext):
    # Async: сохраняем пользователя в PostgreSQL
    user = await get_or_create_user(
        message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        language_code=message.from_user.language_code,
    )

    # Deep link / реферальный payload
    args = message.text.split(maxsplit=1)[1] if len(message.text.split()) > 1 else ''

    if args and args.startswith("plant_"):
        plant_id = args[len("plant_"):]
        plant_url = f"{MINI_APP_URL}?screen=plants&id={plant_id}"
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(
                text="🌿 Открыть растение в ВашСад",
                web_app=WebAppInfo(url=plant_url),
            )
        )
        await message.answer(
            "🌱 Открываем растение в ВашСад...",
            reply_markup=builder.as_markup(),
        )
        return

    if args and args.startswith("diag_"):
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(
                text="🌿 Открыть ВашСад",
                web_app=WebAppInfo(url=MINI_APP_URL),
            )
        )
        await message.answer(
            "🔍 Открываем диагностику в ВашСад...",
            reply_markup=builder.as_markup(),
        )
        return

    # Screen deep links
    if args in SCREEN_LINKS:
        label, screen = SCREEN_LINKS[args]
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text=f'Открыть {label}', web_app=WebAppInfo(url=f'{MINI_APP_URL}?screen={screen}'))
        ]])
        await message.answer(
            f'🌿 Открываю <b>{label}</b> в приложении...',
            reply_markup=kb,
            parse_mode='HTML'
        )
        return

    payload = args or ""
    if payload.startswith("ref_"):
        from services.database import apply_referral
        applied = await apply_referral(message.from_user.id, payload[4:])
        if applied:
            await message.answer(
                "🎁 <b>Реферальный бонус!</b>\n\n"
                "Вам начислено <b>+3 бесплатных сообщения</b> от друга 🌿",
                parse_mode="HTML",
            )

    # Onboarding-квиз отключён (F1.2): профиль (регион/площадь/стиль)
    # заполняется через Mini App картинками, не текстовой FSM-анкетой в боте.
    # from handlers.onboarding import maybe_start_onboarding
    # await maybe_start_onboarding(message, state, message.from_user.id)

    # A/B тест приветствия
    variant, ab_text = _pick_ab_variant(message.from_user.id)

    # Определяем новый ли пользователь (created_at в пределах 30 сек от now)
    from datetime import timezone
    now_utc = message.date
    is_new_user = False
    if user.created_at:
        created = user.created_at
        if created.tzinfo is None:
            # naive datetime — сравниваем с now() тоже naive
            from datetime import datetime as _dt
            delta = abs((_dt.utcnow() - created).total_seconds())
        else:
            delta = abs((now_utc - created).total_seconds())
        is_new_user = delta < 30

    # Трекинг события /start
    import asyncio as _asyncio
    _asyncio.ensure_future(insert_analytics_event(
        telegram_id=message.from_user.id,
        event_name="start",
        params={"ab_variant": variant, "is_new_user": is_new_user},
    ))

    name = user.first_name or ("friend" if user.lang == "en" else "друг")
    greeting = "👋 Hello, {name}!\n\n" if user.lang == "en" else "👋 Привет, {name}!\n\n"
    welcome_text = t("welcome", user.lang).format(bot_name=BOT_NAME, designer_name=DESIGNER_NAME_GEN)
    caption = greeting.format(name=name) + welcome_text
    if WELCOME_IMAGE_URL:
        await message.answer_photo(
            photo=WELCOME_IMAGE_URL,
            caption=caption,
            reply_markup=mini_app_keyboard(),
            parse_mode="HTML",
        )
    else:
        await message.answer(
            caption,
            reply_markup=mini_app_keyboard(),
            parse_mode="HTML",
        )
    await message.answer(
        t("menu_hint", user.lang),
        reply_markup=MAIN_KEYBOARD,
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
        WELCOME_TEXT.format(bot_name=BOT_NAME, designer_name=DESIGNER_NAME_GEN),
        reply_markup=mini_app_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "cancel")
async def cb_cancel(callback: CallbackQuery):
    await callback.message.edit_text(
        WELCOME_TEXT.format(bot_name=BOT_NAME, designer_name=DESIGNER_NAME_GEN),
        reply_markup=mini_app_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(Command("profile"))
async def cmd_profile(message: Message):
    user = await get_or_create_user(
        message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
    )
    status = "⭐ Сад Про (безлимит)" if user.is_subscribed else "🆓 Бесплатный"
    rem_chat   = max(0, FREE_CHAT_LIMIT   - user.chat_count)
    rem_photo  = max(0, FREE_PHOTO_LIMIT  - user.photo_count)
    rem_plants = max(0, FREE_PLANTS_LIMIT - user.plants_count)
    reg_date = user.created_at.strftime("%d.%m.%Y") if user.created_at else "—"

    builder = InlineKeyboardBuilder()
    if not user.is_subscribed:
        builder.row(InlineKeyboardButton(text="⭐ Оформить Сад Про", callback_data="menu:subscribe"))
    builder.row(InlineKeyboardButton(text="◀️ Главное меню", callback_data="menu:main"))

    await message.answer(
        f"👤 <b>Ваш профиль</b>\n\n"
        f"Имя: {user.first_name or '—'}\n"
        f"Статус: <b>{status}</b>\n"
        f"В ВашСад с: {reg_date}\n\n"
        f"<b>Осталось в этом месяце:</b>\n"
        f"💬 AI-чат: {rem_chat} из {FREE_CHAT_LIMIT}\n"
        f"📸 Фото-диагностика: {rem_photo} из {FREE_PHOTO_LIMIT}\n"
        f"🌱 Подбор растений: {rem_plants} из {FREE_PLANTS_LIMIT}",
        parse_mode="HTML",
        reply_markup=builder.as_markup(),
    )


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


# ── Быстрые ответы (ReplyKeyboard) ───────────────────────────────────────────

@router.message(F.text == "🌺 Растения")
async def quick_plants(message: Message, state: FSMContext):
    from handlers.plants import cmd_plants
    await cmd_plants(message, state)


@router.message(F.text == "📸 Диагностика")
async def quick_diagnosis(message: Message):
    await message.answer(
        "📸 Отправьте фото растения для диагностики\n\nФотографируйте крупно, при хорошем освещении"
    )


@router.message(F.text == "📋 Заказать услугу")
async def quick_order(message: Message, state: FSMContext):
    from handlers.order import cmd_order
    await cmd_order(message)


@router.message(F.text == "💬 AI-чат")
async def quick_chat(message: Message):
    await message.answer("💬 Напишите ваш вопрос о саде — отвечу на основе AI!")


@router.message(F.text == "📅 Консультация")
async def quick_book(message: Message, state: FSMContext):
    from handlers.booking import cmd_book
    await cmd_book(message, state)


@router.message(F.text == "👤 Профиль")
async def quick_profile(message: Message):
    await cmd_profile(message)


# ── /callback — запрос обратного звонка ──────────────────────────────────────

from aiogram.fsm.state import State, StatesGroup


class CallbackForm(StatesGroup):
    waiting_phone = State()


@router.message(Command("callback"))
async def cmd_callback(message: Message, state: FSMContext):
    await message.answer(
        "📞 <b>Обратный звонок</b>\n\n"
        "Введите ваш номер телефона, и дизайнер свяжется с вами в течение дня:\n\n"
        "<i>Пример: +7 (999) 123-45-67</i>",
        parse_mode="HTML",
        reply_markup=ReplyKeyboardRemove(),
    )
    await state.set_state(CallbackForm.waiting_phone)


@router.message(CallbackForm.waiting_phone)
async def process_callback_phone(message: Message, state: FSMContext):
    phone = message.text.strip() if message.text else ""
    await state.clear()

    # Notify designer
    import os
    import aiohttp
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    designer_id = os.getenv("DESIGNER_TELEGRAM_ID")
    name = message.from_user.first_name or "Пользователь"
    username = f" (@{message.from_user.username})" if message.from_user.username else ""

    if bot_token and designer_id:
        text = (
            f"📞 Новый запрос на звонок!\n"
            f"Имя: {name}{username}\n"
            f"Телефон: {phone}\n"
            f"Удобное время: Любое время"
        )
        try:
            async with aiohttp.ClientSession() as session:
                await session.post(
                    f"https://api.telegram.org/bot{bot_token}/sendMessage",
                    json={"chat_id": designer_id, "text": text},
                    timeout=aiohttp.ClientTimeout(total=10),
                )
        except Exception:
            pass

    await message.answer(
        "✅ <b>Запрос отправлен!</b>\n\n"
        f"Дизайнер получил ваш номер <b>{phone}</b> и свяжется с вами в течение дня 🌿",
        parse_mode="HTML",
        reply_markup=MAIN_KEYBOARD,
    )
