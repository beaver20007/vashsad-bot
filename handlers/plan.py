"""Хендлер генерации плана участка — пошаговый FSM"""
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton

from keyboards import back_to_menu_keyboard, cancel_keyboard, plan_result_keyboard
from services.ai import ask_claude

router = Router()


class PlanForm(StatesGroup):
    waiting_area    = State()  # Шаг 1: площадь (текст)
    waiting_relief  = State()  # Шаг 2: рельеф (кнопки)
    waiting_style   = State()  # Шаг 3: стиль (кнопки)
    waiting_zones   = State()  # Шаг 4: что важно (кнопки)
    waiting_wishes  = State()  # Шаг 5: свободный комментарий (текст)


def _progress(step: int, total: int = 5) -> str:
    filled = "🟢" * step + "⚪️" * (total - step)
    return f"{filled}  Шаг {step} из {total}\n\n"


@router.message(Command("plan"))
async def cmd_plan(message: Message, state: FSMContext):
    await _start_plan(message, state)


@router.callback_query(F.data == "menu:plan")
async def cb_plan(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await _start_plan(callback.message, state, edit=True)


async def _start_plan(message: Message, state: FSMContext, edit: bool = False):
    await state.set_state(PlanForm.waiting_area)
    text = (
        _progress(1) +
        "🗺 <b>Создаём план вашего участка</b>\n\n"
        "Какова площадь вашего участка?\n"
        "<i>Напишите цифрой, например: 6, 12, 25 соток</i>"
    )
    if edit:
        await message.edit_text(text, parse_mode="HTML", reply_markup=cancel_keyboard())
    else:
        await message.answer(text, parse_mode="HTML", reply_markup=cancel_keyboard())


# ── Шаг 1: площадь → шаг 2 ──────────────────────────────────
@router.message(PlanForm.waiting_area)
async def plan_area(message: Message, state: FSMContext):
    await state.update_data(area=message.text)

    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🏔 Склон", callback_data="relief:склон"),
        InlineKeyboardButton(text="🌊 Низина", callback_data="relief:низина"),
    )
    builder.row(
        InlineKeyboardButton(text="⬜ Ровный", callback_data="relief:ровный"),
        InlineKeyboardButton(text="🤷 Не знаю", callback_data="relief:не знаю"),
    )
    builder.row(InlineKeyboardButton(text="◀️ Отмена", callback_data="cancel"))

    await message.answer(
        _progress(2) +
        "🏔 <b>Какой рельеф на участке?</b>",
        parse_mode="HTML",
        reply_markup=builder.as_markup(),
    )
    await state.set_state(PlanForm.waiting_relief)


# ── Шаг 2: рельеф → шаг 3 ───────────────────────────────────
@router.callback_query(F.data.startswith("relief:"), PlanForm.waiting_relief)
async def plan_relief(callback: CallbackQuery, state: FSMContext):
    await state.update_data(relief=callback.data.split(":", 1)[1])

    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🌿 Природный", callback_data="style:природный"),
        InlineKeyboardButton(text="🏛 Регулярный", callback_data="style:регулярный"),
    )
    builder.row(
        InlineKeyboardButton(text="🌾 Кантри", callback_data="style:кантри"),
        InlineKeyboardButton(text="🔲 Минимализм", callback_data="style:минимализм"),
    )
    builder.row(
        InlineKeyboardButton(text="🤷 Помогите выбрать", callback_data="style:не знаю"),
    )
    builder.row(InlineKeyboardButton(text="◀️ Отмена", callback_data="cancel"))

    await callback.message.edit_text(
        _progress(3) +
        "🎨 <b>Какой стиль сада вам нравится?</b>",
        parse_mode="HTML",
        reply_markup=builder.as_markup(),
    )
    await state.set_state(PlanForm.waiting_style)
    await callback.answer()


# ── Шаг 3: стиль → шаг 4 ────────────────────────────────────
@router.callback_query(F.data.startswith("style:"), PlanForm.waiting_style)
async def plan_style(callback: CallbackQuery, state: FSMContext):
    await state.update_data(style=callback.data.split(":", 1)[1])

    builder = InlineKeyboardBuilder()
    zones = [
        ("🌿 Красивый сад", "zone:красивый сад"),
        ("🥦 Огород", "zone:огород"),
        ("☕ Зона отдыха", "zone:зона отдыха"),
        ("🍎 Плодовый сад", "zone:плодовый сад"),
        ("👶 Детская площадка", "zone:детская площадка"),
        ("🚗 Парковка", "zone:парковка"),
    ]
    for text, data in zones:
        builder.row(InlineKeyboardButton(text=text, callback_data=data))
    builder.row(InlineKeyboardButton(text="◀️ Отмена", callback_data="cancel"))

    await callback.message.edit_text(
        _progress(4) +
        "🏡 <b>Что главное для вас на участке?</b>\n"
        "<i>Выберите один приоритет</i>",
        parse_mode="HTML",
        reply_markup=builder.as_markup(),
    )
    await state.set_state(PlanForm.waiting_zones)
    await callback.answer()


# ── Шаг 4: зоны → шаг 5 ─────────────────────────────────────
@router.callback_query(F.data.startswith("zone:"), PlanForm.waiting_zones)
async def plan_zones(callback: CallbackQuery, state: FSMContext):
    await state.update_data(zones=callback.data.split(":", 1)[1])
    await state.set_state(PlanForm.waiting_wishes)

    await callback.message.edit_text(
        _progress(5) +
        "💬 <b>Последний вопрос!</b>\n\n"
        "Есть ли особые пожелания?\n"
        "<i>Например: нужна живая изгородь, "
        "хочу много цветов весной, аллергия на тополь и т.д.\n\n"
        "Или напишите «нет» если всё уже сказано.</i>",
        parse_mode="HTML",
        reply_markup=cancel_keyboard(),
    )
    await callback.answer()


# ── Шаг 5: пожелания → генерация плана ──────────────────────
@router.message(PlanForm.waiting_wishes)
async def plan_generate(message: Message, state: FSMContext):
    data = await state.get_data()
    wishes = message.text if message.text.lower() != "нет" else "особых пожеланий нет"
    await state.clear()

    # Показываем промежуточное сообщение
    await message.answer(
        "⏳ <b>Составляю план...</b>\n\n"
        f"📐 Площадь: <b>{data.get('area')} соток</b>\n"
        f"🏔 Рельеф: <b>{data.get('relief')}</b>\n"
        f"🎨 Стиль: <b>{data.get('style')}</b>\n"
        f"🏡 Приоритет: <b>{data.get('zones')}</b>",
        parse_mode="HTML",
    )
    await message.bot.send_chat_action(message.chat.id, "typing")

    prompt = f"""Составь текстовый план участка для природного сада.

Параметры:
- Площадь: {data.get('area')} соток
- Рельеф: {data.get('relief')}
- Стиль: {data.get('style')}
- Главная зона: {data.get('zones')}
- Пожелания: {wishes}
- Регион: Средняя полоса России, климатическая зона 4-5

Структура ответа (кратко и по делу):

🗺 ЗОНИРОВАНИЕ
Опиши 3-4 основные зоны с примерными процентами площади.

🌿 РАСТЕНИЯ
5 конкретных растений для природного стиля с кратким описанием.

📋 С ЧЕГО НАЧАТЬ
3 первых шага в правильном порядке.

В конце: одно предложение — предложи заказать детальный проект, нажав кнопку «Заказать проект» ниже."""

    result = await ask_claude([{"role": "user", "content": prompt}])

    await message.answer(
        f"🗺 <b>План вашего участка готов!</b>\n\n{result}",
        parse_mode="HTML",
        reply_markup=plan_result_keyboard(),
    )
