"""Клавиатуры ВашСад Бот"""
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def main_menu_keyboard() -> InlineKeyboardMarkup:
    """Главное меню.
    NB (докс-трек Б, 2026-10-03): эта функция нигде не вызывается — реальное
    главное меню строит handlers.start.mini_app_keyboard(). Оставлена и
    синхронизирована (добавлена кнопка записи) на случай будущего
    использования; не трогать без проверки вызывающего кода."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🗺 План участка", callback_data="menu:plan"),
        InlineKeyboardButton(text="🌱 Подбор растений", callback_data="menu:plants"),
    )
    builder.row(
        InlineKeyboardButton(text="📸 Фото-диагностика", callback_data="menu:photo"),
        InlineKeyboardButton(text="💬 AI-консультация", callback_data="menu:chat"),
    )
    builder.row(
        InlineKeyboardButton(text="💰 Прайс-лист", callback_data="menu:price"),
        InlineKeyboardButton(text="📞 Заказать проект", callback_data="menu:order"),
    )
    builder.row(
        InlineKeyboardButton(text="📅 Записаться на консультацию", callback_data="menu:book"),
    )
    return builder.as_markup()


def price_keyboard() -> InlineKeyboardMarkup:
    """Кнопки к прайс-листу"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📋 Заказать стартовую услугу", callback_data="order:start"),
    )
    builder.row(
        InlineKeyboardButton(text="🏡 Рассчитать стоимость проекта", callback_data="order:project"),
    )
    builder.row(
        InlineKeyboardButton(text="◀️ Главное меню", callback_data="menu:main"),
    )
    return builder.as_markup()


def order_confirm_keyboard(service_key: str) -> InlineKeyboardMarkup:
    """Подтверждение заказа услуги"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Подтвердить заказ", callback_data=f"confirm:{service_key}"),
        InlineKeyboardButton(text="◀️ Назад", callback_data="order:start"),
    )
    return builder.as_markup()


def cancel_keyboard() -> InlineKeyboardMarkup:
    """Кнопка отмены FSM"""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="cancel"))
    return builder.as_markup()


def back_to_menu_keyboard() -> InlineKeyboardMarkup:
    """Просто кнопка «В меню»"""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="◀️ Главное меню", callback_data="menu:main"))
    return builder.as_markup()


def plan_result_keyboard() -> InlineKeyboardMarkup:
    """Кнопки после результата плана: Заказать проект + В меню"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📋 Заказать проект", callback_data="order:project"),
        InlineKeyboardButton(text="◀️ В меню", callback_data="menu:main"),
    )
    return builder.as_markup()


def plants_region_keyboard() -> InlineKeyboardMarkup:
    """Выбор региона для подбора растений"""
    builder = InlineKeyboardBuilder()
    regions = [
        ("🏙 Москва и МО", "msk"),
        ("🌊 Санкт-Петербург", "spb"),
        ("❄️ Урал / Сибирь", "siberia"),
        ("☀️ Юг России", "south"),
        ("🌿 Другой регион", "other"),
    ]
    for name, code in regions:
        builder.row(InlineKeyboardButton(text=name, callback_data=f"region:{code}"))
    builder.row(InlineKeyboardButton(text="◀️ Отмена", callback_data="cancel"))
    return builder.as_markup()


def plants_type_keyboard() -> InlineKeyboardMarkup:
    """Тип растений"""
    builder = InlineKeyboardBuilder()
    types = [
        ("🌸 Цветники и многолетники", "flowers"),
        ("🌳 Деревья и кустарники", "trees"),
        ("🌿 Живая изгородь", "hedge"),
        ("🍅 Плодовый сад / огород", "fruit"),
        ("🌱 Газон", "lawn"),
        ("🎋 Экзотика / необычное", "exotic"),
    ]
    for name, code in types:
        builder.row(InlineKeyboardButton(text=name, callback_data=f"plant_type:{code}"))
    builder.row(InlineKeyboardButton(text="◀️ Отмена", callback_data="cancel"))
    return builder.as_markup()

