"""Хендлер подбора растений"""
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from config import FREE_PLANTS_LIMIT
from keyboards import (
    plants_region_keyboard, plants_type_keyboard,
    back_to_menu_keyboard, subscribe_keyboard, cancel_keyboard, plan_result_keyboard
)
from services.storage import get_or_create_user, can_use_plants, update_user
from services.ai import select_plants

router = Router()


class PlantsForm(StatesGroup):
    waiting_region = State()
    waiting_type = State()
    waiting_light = State()


REGION_NAMES = {
    "msk": "Москва и Московская область",
    "spb": "Санкт-Петербург и Ленобласть",
    "siberia": "Урал / Сибирь",
    "south": "Юг России (Краснодарский край и юг)",
    "other": "Другой регион России",
}

PLANT_TYPE_NAMES = {
    "flowers": "Цветники и многолетники",
    "trees": "Деревья и кустарники",
    "hedge": "Живая изгородь",
    "fruit": "Плодовый сад / огород",
    "lawn": "Газон",
    "exotic": "Экзотика / необычное",
}


@router.message(Command("plants"))
async def cmd_plants(message: Message, state: FSMContext):
    await _start_plants_flow(message, state)


@router.callback_query(F.data == "menu:plants")
async def cb_plants(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await _start_plants_flow(callback.message, state, edit=True)


async def _start_plants_flow(message: Message, state: FSMContext, edit: bool = False):
    user = get_or_create_user(message.chat.id)

    if not can_use_plants(user, FREE_PLANTS_LIMIT):
        text = (
            f"⚠️ Лимит бесплатных запросов подбора исчерпан.\n\n"
            f"Оформите подписку <b>«Сад Про»</b> за безлимитный подбор!"
        )
        kb = subscribe_keyboard()
        if edit:
            await message.edit_text(text, parse_mode="HTML", reply_markup=kb)
        else:
            await message.answer(text, parse_mode="HTML", reply_markup=kb)
        return

    await state.set_state(PlantsForm.waiting_region)
    text = "🌱 <b>Подбор растений</b>\n\nВыберите ваш регион:"
    if edit:
        await message.edit_text(text, parse_mode="HTML", reply_markup=plants_region_keyboard())
    else:
        await message.answer(text, parse_mode="HTML", reply_markup=plants_region_keyboard())


@router.callback_query(F.data.startswith("region:"), PlantsForm.waiting_region)
async def cb_region(callback: CallbackQuery, state: FSMContext):
    region_code = callback.data.split(":")[1]
    await state.update_data(region=REGION_NAMES.get(region_code, region_code))
    await state.set_state(PlantsForm.waiting_type)
    await callback.message.edit_text(
        "🌸 Отлично! Теперь выберите, что хотите посадить:",
        reply_markup=plants_type_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("plant_type:"), PlantsForm.waiting_type)
async def cb_plant_type(callback: CallbackQuery, state: FSMContext):
    plant_type = callback.data.split(":")[1]
    await state.update_data(plant_type=PLANT_TYPE_NAMES.get(plant_type, plant_type))
    await state.set_state(PlantsForm.waiting_light)

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="☀️ Солнце (6+ ч)", callback_data="light:sun"),
        InlineKeyboardButton(text="⛅ Полутень", callback_data="light:partial"),
    )
    builder.row(
        InlineKeyboardButton(text="🌑 Тень", callback_data="light:shade"),
        InlineKeyboardButton(text="🤷 Не знаю", callback_data="light:unknown"),
    )
    builder.row(InlineKeyboardButton(text="◀️ Отмена", callback_data="cancel"))

    await callback.message.edit_text(
        "☀️ Какое освещение на вашем участке?",
        reply_markup=builder.as_markup(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("light:"), PlantsForm.waiting_light)
async def cb_light(callback: CallbackQuery, state: FSMContext):
    light_map = {
        "sun": "Солнечное место (6+ часов в день)",
        "partial": "Полутень (3–6 часов)",
        "shade": "Тень (менее 3 часов)",
        "unknown": "Не определено",
    }
    light = light_map.get(callback.data.split(":")[1], "не указано")
    await state.update_data(light=light)

    data = await state.get_data()
    await state.clear()

    # Проверяем лимит и обновляем счётчик
    user = get_or_create_user(callback.from_user.id)
    if not user.is_subscribed:
        user.plants_count += 1
        update_user(user)

    await callback.message.edit_text(
        "🔍 <b>Подбираю растения для вас...</b>\n\n"
        f"📍 Регион: {data.get('region')}\n"
        f"🌱 Тип: {data.get('plant_type')}\n"
        f"☀️ Освещение: {light}\n\n"
        "<i>Это займёт несколько секунд...</i>",
        parse_mode="HTML",
    )
    await callback.answer()

    result = await select_plants(data)

    remaining_text = ""
    if not user.is_subscribed:
        remaining = FREE_PLANTS_LIMIT - user.plants_count
        remaining_text = f"\n\n<i>Осталось бесплатных запросов: {remaining}/{FREE_PLANTS_LIMIT}</i>"

    await callback.message.edit_text(
        f"🌱 <b>Подборка растений готова!</b>\n\n{result}{remaining_text}",
        parse_mode="HTML",
        reply_markup=plan_result_keyboard(),
    )
