"""Напоминания о поливе растений."""
import logging
import os
from datetime import datetime, time as dtime
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

router = Router()
log = logging.getLogger(__name__)

class WateringForm(StatesGroup):
    waiting_plants = State()
    waiting_time = State()
    waiting_days = State()

@router.message(Command("watering"))
async def cmd_watering(message: Message):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить напоминание", callback_data="watering:add")],
        [InlineKeyboardButton(text="📋 Мои напоминания", callback_data="watering:list")],
        [InlineKeyboardButton(text="❌ Удалить все", callback_data="watering:clear")],
    ])
    await message.answer("💧 <b>Напоминания о поливе</b>\n\nНастройте расписание полива ваших растений:", reply_markup=keyboard, parse_mode="HTML")

@router.callback_query(F.data == "watering:add")
async def cb_watering_add(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("🌱 Напишите, какие растения нужно поливать (или 'все'):")
    await state.set_state(WateringForm.waiting_plants)
    await callback.answer()

@router.message(WateringForm.waiting_plants)
async def watering_plants(message: Message, state: FSMContext):
    await state.update_data(plants=message.text)
    await message.answer("🕐 В какое время напоминать? Введите время в формате ЧЧ:ММ (например: 08:00)")
    await state.set_state(WateringForm.waiting_time)

@router.message(WateringForm.waiting_time)
async def watering_time(message: Message, state: FSMContext):
    try:
        t = datetime.strptime(message.text.strip(), "%H:%M").time()
    except ValueError:
        await message.answer("Неверный формат. Введите время как ЧЧ:ММ, например 08:30")
        return
    await state.update_data(reminder_time=message.text.strip())
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Каждый день", callback_data="wdays:daily")],
        [InlineKeyboardButton(text="Через день", callback_data="wdays:every2")],
        [InlineKeyboardButton(text="2 раза в неделю", callback_data="wdays:twice")],
        [InlineKeyboardButton(text="Раз в неделю", callback_data="wdays:weekly")],
    ])
    await message.answer("📅 Как часто поливать?", reply_markup=keyboard)
    await state.set_state(WateringForm.waiting_days)

@router.callback_query(F.data.startswith("wdays:"), WateringForm.waiting_days)
async def watering_days(callback: CallbackQuery, state: FSMContext):
    freq = callback.data.split(":")[1]
    data = await state.get_data()
    plants = data.get('plants', 'растения')
    time_str = data.get('reminder_time', '08:00')
    await state.clear()

    freq_labels = {'daily': 'каждый день', 'every2': 'через день', 'twice': '2 раза в неделю', 'weekly': 'раз в неделю'}

    # Save to DB
    from services.database import get_pool
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """CREATE TABLE IF NOT EXISTS watering_reminders (
               id SERIAL PRIMARY KEY, telegram_id BIGINT NOT NULL,
               plants TEXT NOT NULL, reminder_time TIME NOT NULL,
               frequency VARCHAR(20) NOT NULL, active BOOLEAN DEFAULT TRUE,
               created_at TIMESTAMP DEFAULT NOW()
            )""")
        await conn.execute(
            "INSERT INTO watering_reminders (telegram_id, plants, reminder_time, frequency) VALUES ($1, $2, $3::time, $4)",
            callback.from_user.id, plants, time_str, freq
        )

    # Schedule the reminder
    from services.scheduler import schedule_watering_reminder
    await schedule_watering_reminder(callback.bot, callback.from_user.id, plants, time_str, freq)

    await callback.message.edit_text(
        f"✅ <b>Напоминание настроено!</b>\n\n"
        f"🌱 Растения: {plants}\n"
        f"🕐 Время: {time_str}\n"
        f"📅 Частота: {freq_labels.get(freq, freq)}\n\n"
        f"Буду напоминать вам о поливе! 💧",
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(F.data == "watering:list")
async def cb_watering_list(callback: CallbackQuery):
    from services.database import get_pool
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT plants, reminder_time, frequency FROM watering_reminders WHERE telegram_id=$1 AND active=TRUE",
            callback.from_user.id
        )
    if not rows:
        await callback.answer("Нет активных напоминаний", show_alert=True)
        return
    text = "💧 <b>Ваши напоминания о поливе:</b>\n\n"
    for r in rows:
        text += f"🌱 {r['plants']} — {r['reminder_time'].strftime('%H:%M')}, {r['frequency']}\n"
    await callback.message.answer(text, parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data == "watering:clear")
async def cb_watering_clear(callback: CallbackQuery):
    from services.database import get_pool
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("UPDATE watering_reminders SET active=FALSE WHERE telegram_id=$1", callback.from_user.id)
    await callback.answer("❌ Все напоминания удалены", show_alert=True)
