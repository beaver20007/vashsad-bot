"""Хендлер AI-чата по садоводству"""
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from config import FREE_CHAT_LIMIT, SUBSCRIPTION_PRICE
from keyboards import back_to_menu_keyboard, subscribe_keyboard
from services.database import get_or_create_user, can_use_chat, add_message_to_history, update_user, add_bonus_messages
from services.ai import ask_claude, SYSTEM_PROMPT

router = Router()

FAQ_PATTERNS = [
    {
        'keywords': ['цена', 'стоимость', 'сколько стоит', 'прайс', 'расценки', 'тариф'],
        'answer': (
            "💰 <b>Стоимость услуг дизайнера:</b>\n\n"
            "Консультации, проекты и авторский надзор — стоимость зависит "
            "от площади и сложности участка.\n\n"
            "Точный расчёт — в приложении ВашСад или на консультации. "
            "Оформите заявку — посчитаю под ваш участок! 🌿"
        ),
    },
    {
        'keywords': ['сроки', 'срок', 'как долго', 'сколько времени', 'когда готово'],
        'answer': (
            "⏱ <b>Сроки выполнения работ:</b>\n\n"
            "• Консультация — 1–2 часа\n"
            "• Дендроплан — 3–5 дней\n"
            "• Эскизный проект — 7–14 дней\n"
            "• Полный проект — 3–4 недели\n\n"
            "Сроки зависят от загруженности и сложности. "
            "Запишитесь на консультацию для точных сроков! 📅"
        ),
    },
    {
        'keywords': ['как записаться', 'записаться', 'консультация', 'как заказать', 'заказать'],
        'answer': (
            "📅 <b>Как записаться на консультацию:</b>\n\n"
            "1. Нажмите /book или кнопку «📅 Консультация»\n"
            "2. Выберите удобный слот\n"
            "3. Укажите контактный телефон\n\n"
            "Или напишите напрямую — отвечу в течение часа! 🌿"
        ),
    },
    {
        'keywords': ['регион', 'область', 'где работаете', 'выезд', 'нижний', 'владимир'],
        'answer': (
            "📍 <b>География работы:</b>\n\n"
            "Основные регионы: Нижегородская и Владимирская области.\n\n"
            "Выезды возможны в радиусе 200 км от Нижнего Новгорода. "
            "Удалённые консультации — по всей России! 🗺"
        ),
    },
    {
        'keywords': ['гарантия', 'гарантии', 'если не понравится', 'возврат'],
        'answer': (
            "✅ <b>Гарантии:</b>\n\n"
            "• Бесплатные правки в рамках ТЗ\n"
            "• Авторский надзор при реализации\n"
            "• Замена растений при гибели по вине посадки (1 год)\n\n"
            "Работаю по договору с чёткими условиями. 🤝"
        ),
    },
]


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
    for faq in FAQ_PATTERNS:
        if any(kw in text_lower for kw in faq['keywords']):
            return faq['answer']
    return None


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
    user = await get_or_create_user(
        message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
    )

    # Проверяем бонусные сообщения (приоритет над обычным лимитом)
    use_bonus = False
    if not user.is_subscribed and user.bonus_messages > 0:
        use_bonus = True
    elif not can_use_chat(user, FREE_CHAT_LIMIT):
        await message.answer(
            LIMIT_REACHED_TEXT,
            parse_mode="HTML",
            reply_markup=subscribe_keyboard(),
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
        system = SYSTEM_PROMPT + f"\n\nКонтекст пользователя: {region_hint}"
    else:
        system = None

    # Отправляем запрос к Claude с историей для контекста
    response = await ask_claude(user.chat_history, system=system)

    # Сохраняем ответ в историю
    await add_message_to_history(user, "assistant", response)

    # Обновляем счётчик
    if not user.is_subscribed:
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
    else:
        footer = ""

    await message.answer(
        response + footer,
        parse_mode="HTML",
        reply_markup=back_to_menu_keyboard(),
    )
