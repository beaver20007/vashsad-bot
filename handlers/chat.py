"""Хендлер AI-чата по садоводству"""
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from config import FREE_CHAT_LIMIT
from keyboards import back_to_menu_keyboard
from services import bot_texts
from services.ai import ask_claude
from services.database import (
    add_bonus_messages,
    add_message_to_history,
    can_use_chat,
    get_or_create_user,
    update_user,
)

router = Router()

_REGION_CLIMATE: dict[str, str] = {
    "Нижегородская обл.": "Пользователь из Нижегородской области, климатическая зона 4b. Учитывай холодные зимы (до -30°C), короткое лето, суглинистые почвы.",
    "Владимирская обл.": "Пользователь из Владимирской области, климатическая зона 4b. Учитывай холодные зимы, умеренное лето, преимущественно суглинки.",
    "Другой регион": "Пользователь из другого региона России. Уточни климатическую зону при необходимости.",
}


def _region_climate_hint(region: str) -> str:
    """Вернуть климатическую подсказку по region, хранящемуся в БД.
    region может быть либо коротким ('Нижегородская обл.'), либо полной строкой
    онбординга ('Нижегородская обл. · 6–12 соток · Природный')."""
    for key, hint in _REGION_CLIMATE.items():
        if key in region:
            return hint
    # Если регион не распознан — вернуть его как есть
    return f"Пользователь указал регион: {region}."


def check_faq(text: str) -> str | None:
    text_lower = text.lower()
    for faq in bot_texts.get("faq")["items"]:
        if any(kw in text_lower for kw in faq['keywords']):
            return faq['answer']
    return None


# TODO(владелец/Аня): формулировка заглушка. Подписки «Сад Про» больше нет
# (решение владельца 26.09.2026), а что предлагать клиенту при исчерпании
# лимита — не решено (лимиты не сбрасываются, «в месяц» в старом тексте
# было неверно).
LIMIT_REACHED_TEXT = "⚠️ <b>Лимит бесплатных сообщений исчерпан.</b>"


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
    user = await get_or_create_user(
        message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
    )

    # Проверяем бонусные сообщения (приоритет над обычным лимитом)
    use_bonus = False
    if user.bonus_messages > 0:
        use_bonus = True
    elif not can_use_chat(user, FREE_CHAT_LIMIT):
        await message.answer(
            LIMIT_REACHED_TEXT,
            parse_mode="HTML",
            reply_markup=back_to_menu_keyboard(),
        )
        return

    # Проверяем FAQ — отвечаем без вызова Claude API
    faq_answer = check_faq(message.text)
    if faq_answer:
        await message.answer(faq_answer, parse_mode="HTML")
        return

    # Показываем индикатор набора текста
    await message.bot.send_chat_action(message.chat.id, "typing")

    # Добавляем сообщение пользователя в историю
    await add_message_to_history(user, "user", message.text)

    # Формируем системный промпт с учётом региона пользователя
    if user.region:
        region_hint = _region_climate_hint(user.region)
        system = bot_texts.get("system_prompt.chat")["text"] + f"\n\nКонтекст пользователя: {region_hint}"
    else:
        system = None

    # Отправляем запрос к Claude с историей для контекста
    response = await ask_claude(user.chat_history, system=system)

    # Сохраняем ответ в историю
    await add_message_to_history(user, "assistant", response)

    # Обновляем счётчик
    if use_bonus:
        # Списываем бонусное сообщение
        await add_bonus_messages(user.telegram_id, -1)
        user.bonus_messages -= 1
        footer = f"\n\n<i>Использовано бонусное сообщение. Осталось бонусных: {user.bonus_messages}</i>"
    else:
        user.chat_count += 1
        remaining = FREE_CHAT_LIMIT - user.chat_count
        await update_user(user)
        footer = f"\n\n<i>Осталось бесплатных сообщений: {remaining}/{FREE_CHAT_LIMIT}</i>"

    await message.answer(
        response + footer,
        parse_mode="HTML",
        reply_markup=back_to_menu_keyboard(),
    )
