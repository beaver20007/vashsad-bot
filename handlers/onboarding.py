"""Фаза 1: Onboarding-квиз для новых пользователей"""
import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from services import bot_texts
from services.database import get_or_create_user, update_user_region

router = Router()
log = logging.getLogger(__name__)


class OnboardingForm(StatesGroup):
    waiting_region = State()
    waiting_area   = State()
    waiting_style  = State()


REGIONS = [
    ("🏙 Нижегородская обл.", "Нижегородская обл."),
    ("🏰 Владимирская обл.", "Владимирская обл."),
    ("🌆 Другой регион", "Другой регион"),
]
AREAS = ["до 6 соток", "6–12 соток", "12–30 соток", "больше 30 соток"]
STYLES = ["Природный", "Классический", "Современный", "Ещё не знаю"]


async def maybe_start_onboarding(message: Message, state: FSMContext, telegram_id: int):
    """Запускает квиз если у пользователя не заполнен профиль. Вызывается из cmd_start."""
    user = await get_or_create_user(telegram_id)
    if user.region:
        return  # профиль уже заполнен
    await _ask_region(message, state)


async def _ask_region(message: Message, state: FSMContext):
    builder = InlineKeyboardBuilder()
    for label, value in REGIONS:
        builder.row(InlineKeyboardButton(text=label, callback_data=f"ob_region:{value}"))
    await message.answer(
        bot_texts.get("onboarding")["region_prompt"],
        parse_mode="HTML",
        reply_markup=builder.as_markup(),
    )
    await state.set_state(OnboardingForm.waiting_region)


@router.callback_query(OnboardingForm.waiting_region, F.data.startswith("ob_region:"))
async def cb_region(callback: CallbackQuery, state: FSMContext):
    region = callback.data.split(":", 1)[1]
    await state.update_data(region=region)

    builder = InlineKeyboardBuilder()
    for a in AREAS:
        builder.row(InlineKeyboardButton(text=a, callback_data=f"ob_area:{a}"))

    await callback.message.edit_text(
        bot_texts.get("onboarding")["area_prompt"].format(region=region),
        parse_mode="HTML",
        reply_markup=builder.as_markup(),
    )
    await state.set_state(OnboardingForm.waiting_area)
    await callback.answer()


@router.callback_query(OnboardingForm.waiting_area, F.data.startswith("ob_area:"))
async def cb_area(callback: CallbackQuery, state: FSMContext):
    area = callback.data.split(":", 1)[1]
    await state.update_data(area=area)

    builder = InlineKeyboardBuilder()
    for s in STYLES:
        builder.row(InlineKeyboardButton(text=s, callback_data=f"ob_style:{s}"))

    await callback.message.edit_text(
        bot_texts.get("onboarding")["style_prompt"].format(area=area),
        parse_mode="HTML",
        reply_markup=builder.as_markup(),
    )
    await state.set_state(OnboardingForm.waiting_style)
    await callback.answer()


@router.callback_query(OnboardingForm.waiting_style, F.data.startswith("ob_style:"))
async def cb_style(callback: CallbackQuery, state: FSMContext):
    style = callback.data.split(":", 1)[1]
    data = await state.get_data()
    region = data.get("region", "")
    area   = data.get("area", "")

    await update_user_region(callback.from_user.id, f"{region} · {area} · {style}")

    await state.clear()
    from aiogram.utils.keyboard import InlineKeyboardBuilder as IKB
    b = IKB()
    b.row(InlineKeyboardButton(text="▶️ Начать", callback_data="menu:main"))
    await callback.message.edit_text(
        bot_texts.get("onboarding")["saved"].format(region=region, area=area, style=style),
        parse_mode="HTML",
        reply_markup=b.as_markup(),
    )
    await callback.answer()
