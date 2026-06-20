"""Хендлер генерации плана участка — пошаговый FSM"""
import logging
import os
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, BufferedInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton

from keyboards import back_to_menu_keyboard, cancel_keyboard, plan_result_keyboard
from services.ai import ask_claude
from services.pdf_generator import generate_plan_pdf
from services.database import get_or_create_user, save_order
from config import DESIGNER_NAME, DESIGNER_TELEGRAM_ID

router = Router()
log = logging.getLogger(__name__)

DESIGNER_TELEGRAM_ID_2 = int(os.getenv("DESIGNER_TELEGRAM_ID_2", "0"))


class PlanForm(StatesGroup):
    waiting_area    = State()   # Шаг 1: площадь (текст)
    waiting_style   = State()   # Шаг 2: стиль (кнопки)
    waiting_budget  = State()   # Шаг 3: бюджет (кнопки)
    waiting_wishes  = State()   # Шаг 4: свободный комментарий (текст)
    waiting_confirm = State()   # Шаг 5: подтверждение (кнопки)


TOTAL_STEPS = 5


def _progress(step: int, total: int = TOTAL_STEPS) -> str:
    filled = "🟢" * step + "⚪️" * (total - step)
    return f"{filled}  Шаг {step} из {total}\n\n"


async def _notify_designer(bot, plan_data: dict, user, order_id: int):
    """Отправить уведомление дизайнеру о новом запросе на план."""
    name = getattr(user, "full_name", "") or getattr(user, "username", "—")
    username = f"@{user.username}" if getattr(user, "username", None) else "нет"
    text = (
        f"🗺 <b>Новый запрос плана участка #{order_id}</b>\n\n"
        f"👤 Пользователь: {name} ({username})\n"
        f"📐 Площадь: {plan_data.get('area')} соток\n"
        f"🎨 Стиль: {plan_data.get('style')}\n"
        f"💰 Бюджет: {plan_data.get('budget')}\n"
        f"💬 Пожелания: {plan_data.get('wishes')}\n"
    )
    for chat_id in [DESIGNER_TELEGRAM_ID, DESIGNER_TELEGRAM_ID_2]:
        if chat_id:
            try:
                await bot.send_message(chat_id, text, parse_mode="HTML")
            except Exception as e:
                log.error(f"Не удалось уведомить дизайнера {chat_id}: {e}")


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


# ── Шаг 1: площадь → шаг 2 (стиль) ────────────────────────────
@router.message(PlanForm.waiting_area)
async def plan_area(message: Message, state: FSMContext):
    await state.update_data(area=message.text.strip())

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

    await message.answer(
        _progress(2) +
        "🎨 <b>Какой стиль сада вам нравится?</b>",
        parse_mode="HTML",
        reply_markup=builder.as_markup(),
    )
    await state.set_state(PlanForm.waiting_style)


# ── Шаг 2: стиль → шаг 3 (бюджет) ──────────────────────────
@router.callback_query(F.data.startswith("style:"), PlanForm.waiting_style)
async def plan_style(callback: CallbackQuery, state: FSMContext):
    await state.update_data(style=callback.data.split(":", 1)[1])

    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="💸 до 100 000 ₽", callback_data="budget:до 100к"))
    builder.row(InlineKeyboardButton(text="💰 100 000 – 300 000 ₽", callback_data="budget:100-300к"))
    builder.row(InlineKeyboardButton(text="💎 от 300 000 ₽", callback_data="budget:300к+"))
    builder.row(InlineKeyboardButton(text="◀️ Отмена", callback_data="cancel"))

    await callback.message.edit_text(
        _progress(3) +
        "💰 <b>Какой примерный бюджет на благоустройство?</b>",
        parse_mode="HTML",
        reply_markup=builder.as_markup(),
    )
    await state.set_state(PlanForm.waiting_budget)
    await callback.answer()


# ── Шаг 3: бюджет → шаг 4 (пожелания) ──────────────────────
@router.callback_query(F.data.startswith("budget:"), PlanForm.waiting_budget)
async def plan_budget(callback: CallbackQuery, state: FSMContext):
    await state.update_data(budget=callback.data.split(":", 1)[1])
    await state.set_state(PlanForm.waiting_wishes)

    await callback.message.edit_text(
        _progress(4) +
        "💬 <b>Есть особые пожелания?</b>\n\n"
        "<i>Например: нужна живая изгородь, хочу много цветов весной, "
        "аллергия на тополь, нужна зона барбекю…\n\n"
        "Или напишите «нет», если всё уже сказано.</i>",
        parse_mode="HTML",
        reply_markup=cancel_keyboard(),
    )
    await callback.answer()


# ── Шаг 4: пожелания → шаг 5 (подтверждение) ───────────────
@router.message(PlanForm.waiting_wishes)
async def plan_wishes(message: Message, state: FSMContext):
    await state.update_data(wishes=message.text.strip())
    data = await state.get_data()

    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Подтвердить", callback_data="plan:confirm"),
        InlineKeyboardButton(text="🔄 Начать заново", callback_data="plan:restart"),
    )

    await message.answer(
        _progress(5) +
        "📋 <b>Проверьте данные вашего участка:</b>\n\n"
        f"📐 Площадь: <b>{data.get('area')} соток</b>\n"
        f"🎨 Стиль: <b>{data.get('style')}</b>\n"
        f"💰 Бюджет: <b>{data.get('budget')}</b>\n"
        f"💬 Пожелания: <b>{data.get('wishes')}</b>\n\n"
        "Всё верно? Нажмите <b>Подтвердить</b> — составим план!",
        parse_mode="HTML",
        reply_markup=builder.as_markup(),
    )
    await state.set_state(PlanForm.waiting_confirm)


# ── Шаг 5: начать заново ────────────────────────────────────
@router.callback_query(F.data == "plan:restart", PlanForm.waiting_confirm)
async def plan_restart(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    await _start_plan(callback.message, state, edit=True)


# ── Шаг 5: подтверждение → генерация плана ──────────────────
@router.callback_query(F.data == "plan:confirm", PlanForm.waiting_confirm)
async def plan_generate(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    await state.clear()

    wishes = data.get("wishes", "")
    if wishes.lower() in ("нет", "no", "-", ""):
        wishes = "особых пожеланий нет"

    # Показываем промежуточное сообщение
    await callback.message.edit_text(
        "⏳ <b>Составляю план...</b>\n\n"
        f"📐 Площадь: <b>{data.get('area')} соток</b>\n"
        f"🎨 Стиль: <b>{data.get('style')}</b>\n"
        f"💰 Бюджет: <b>{data.get('budget')}</b>",
        parse_mode="HTML",
    )
    await callback.message.bot.send_chat_action(callback.message.chat.id, "typing")

    prompt = f"""Составь текстовый план участка для природного сада.

Параметры:
- Площадь: {data.get('area')} соток
- Стиль: {data.get('style')}
- Бюджет: {data.get('budget')}
- Пожелания: {wishes}
- Регион: Средняя полоса России, климатическая зона 4-5

Структура ответа (кратко и по делу):

🗺 ЗОНИРОВАНИЕ
Опиши 3-4 основные зоны с примерными процентами площади.

🌿 РАСТЕНИЯ
5 конкретных растений для выбранного стиля с кратким описанием.

💰 БЮДЖЕТ
Укажи примерное распределение бюджета по статьям (посадочный материал, работы, материалы).

📋 С ЧЕГО НАЧАТЬ
3 первых шага в правильном порядке.

В конце: одно предложение — предложи заказать детальный проект, нажав кнопку «Заказать проект» ниже."""

    result = await ask_claude([{"role": "user", "content": prompt}])

    # Сохраняем заявку в БД
    telegram_id = callback.from_user.id
    order_id = 0
    try:
        await get_or_create_user(
            telegram_id=telegram_id,
            username=callback.from_user.username,
            full_name=callback.from_user.full_name,
        )
        order_id = await save_order(
            telegram_id=telegram_id,
            service_type="plan",
            service_name="Генерация плана участка",
            area=data.get("area"),
            style=data.get("style"),
            wishes=f"Бюджет: {data.get('budget')}. {wishes}",
        )
        log.info(f"Plan order #{order_id} saved for user {telegram_id}")
    except Exception as e:
        log.error(f"Не удалось сохранить план в БД: {e}")

    # Уведомляем дизайнера
    try:
        await _notify_designer(callback.message.bot, {**data, "wishes": wishes}, callback.from_user, order_id)
    except Exception as e:
        log.error(f"Не удалось уведомить дизайнера: {e}")

    await callback.message.answer(
        f"🗺 <b>План вашего участка готов!</b>\n\n{result}",
        parse_mode="HTML",
        reply_markup=plan_result_keyboard(),
    )

    # ── Генерация и отправка PDF ──────────────────────────────────
    try:
        user = callback.from_user
        user_name = user.full_name if user else "Клиент"
        pdf_bytes = generate_plan_pdf(
            plan_text=result,
            user_name=user_name,
            area=data.get("area", "—"),
            style=data.get("style", "—"),
            designer_name=DESIGNER_NAME,
        )
        await callback.message.answer_document(
            BufferedInputFile(pdf_bytes, filename="план_сада.pdf"),
            caption="📄 PDF-версия вашего плана сада",
        )
    except Exception as e:
        log.warning("PDF generation failed: %s", e)
