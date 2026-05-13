"""Хендлер AI-чата по садоводству"""
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from config import FREE_CHAT_LIMIT, SUBSCRIPTION_PRICE
from keyboards import back_to_menu_keyboard, subscribe_keyboard
from services.storage import get_or_create_user, can_use_chat, add_message_to_history, update_user
from services.ai import ask_claude

router = Router()

LIMIT_REACHED_TEXT = (
    f"⚠️ <b>Лимит бесплатных сообщений исчерпан</b>\n\n"
    f"В бесплатном режиме доступно {FREE_CHAT_LIMIT} AI-сообщений в месяц.\n\n"
    f"Оформите подписку <b>«Сад Про»</b> за {SUBSCRIPTION_PRICE} ₽/мес "
    f"и получите безлимитные консультации + скидку 10% на все услуги!"
)


@router.message(Command("chat"))
async def cmd_chat(message: Message):
    await message.answer(
        "💬 <b>AI-консультация по садоводству</b>\n\n"
        "Задайте любой вопрос:\n"
        "• Какие растения посадить в тени?\n"
        "• Как ухаживать за розами?\n"
        "• Чем болеет моя туя?\n"
        "• Как спланировать огород?\n\n"
        "<i>Просто напишите ваш вопрос ↓</i>",
        parse_mode="HTML",
        reply_markup=back_to_menu_keyboard(),
    )


@router.callback_query(F.data == "menu:chat")
async def cb_chat(callback: CallbackQuery):
    await callback.message.edit_text(
        "💬 <b>AI-консультация по садоводству</b>\n\n"
        "Задайте любой вопрос по садоводству и ландшафтному дизайну.\n\n"
        "<i>Просто напишите ваш вопрос ↓</i>",
        parse_mode="HTML",
        reply_markup=back_to_menu_keyboard(),
    )
    await callback.answer()


@router.message(F.text & ~F.text.startswith("/"))
async def handle_text_message(message: Message):
    """Обрабатываем любое текстовое сообщение как вопрос к AI"""
    user = get_or_create_user(
        message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
    )

    # Проверяем лимит
    if not can_use_chat(user, FREE_CHAT_LIMIT):
        await message.answer(
            LIMIT_REACHED_TEXT,
            parse_mode="HTML",
            reply_markup=subscribe_keyboard(),
        )
        return

    # Показываем индикатор набора текста
    await message.bot.send_chat_action(message.chat.id, "typing")

    # Добавляем сообщение пользователя в историю
    add_message_to_history(user, "user", message.text)

    # Отправляем запрос к Claude с историей для контекста
    response = await ask_claude(user.chat_history)

    # Сохраняем ответ в историю
    add_message_to_history(user, "assistant", response)

    # Обновляем счётчик
    if not user.is_subscribed:
        user.chat_count += 1
        remaining = FREE_CHAT_LIMIT - user.chat_count
        update_user(user)
        footer = f"\n\n<i>Осталось бесплатных сообщений: {remaining}/{FREE_CHAT_LIMIT}</i>"
    else:
        footer = ""

    await message.answer(
        response + footer,
        parse_mode="HTML",
        reply_markup=back_to_menu_keyboard(),
    )
