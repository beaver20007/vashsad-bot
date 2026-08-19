"""
🌿 Питомники растений — /nurseries
Показывает питомники по региону пользователя
"""

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from services.database import get_or_create_user

router = Router()

NURSERIES: dict[str, list[dict]] = {
    "нижегородская": [
        {
            "name": "Питомник «Зелёный дом»",
            "address": "Нижний Новгород, ул. Садовая, 12",
            "phone": "+7 (831) 234-56-78",
            "url": "https://2gis.ru/nizhny_novgorod",
            "rating": 4.7,
            "types": ["многолетники", "розы", "хвойные"],
        },
        {
            "name": "Сад «Природный стиль»",
            "address": "Кстово, ул. Лесная, 5",
            "phone": "+7 (831) 345-67-89",
            "url": "https://2gis.ru/nizhny_novgorod",
            "rating": 4.5,
            "types": ["злаки", "многолетники", "водные растения"],
        },
        {
            "name": "Питомник «Нижегородский»",
            "address": "Нижний Новгород, ул. Победы, 43",
            "phone": "+7 (831) 456-78-90",
            "url": "https://2gis.ru/nizhny_novgorod",
            "rating": 4.3,
            "types": ["деревья", "кустарники", "луковичные"],
        },
    ],
    "владимирская": [
        {
            "name": "Питомник «Владимирский сад»",
            "address": "Владимир, ул. Садоводческая, 8",
            "phone": "+7 (492) 234-56-78",
            "url": "https://2gis.ru/vladimir",
            "rating": 4.6,
            "types": ["плодовые", "ягодные", "декоративные"],
        },
        {
            "name": "Флора «Суздаль»",
            "address": "Суздаль, ул. Торговая, 15",
            "phone": "+7 (492) 345-67-89",
            "url": "https://2gis.ru/vladimir",
            "rating": 4.8,
            "types": ["редкие многолетники", "розы", "клематисы"],
        },
    ],
    "московская": [
        {
            "name": "Питомник «Подмосковье»",
            "address": "Химки, ул. Лесопарковая, 22",
            "phone": "+7 (495) 234-56-78",
            "url": "https://2gis.ru/moscow",
            "rating": 4.4,
            "types": ["хвойные", "лиственные", "многолетники"],
        },
    ],
}

REGION_LABELS = {
    "нижегородская": "🏙 Нижегородская",
    "владимирская": "🏰 Владимирская",
    "московская": "🌆 Другой",
}

DEFAULT_REGION = "нижегородская"


def _region_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🏙 Нижегородская", callback_data="nurseries_region:нижегородская"),
            InlineKeyboardButton(text="🏰 Владимирская", callback_data="nurseries_region:владимирская"),
        ],
        [
            InlineKeyboardButton(text="🌆 Другой", callback_data="nurseries_region:московская"),
        ],
    ])


def _format_nurseries(region: str) -> str:
    nurseries = NURSERIES.get(region, NURSERIES[DEFAULT_REGION])
    region_label = REGION_LABELS.get(region, region.capitalize())
    lines = [f"<b>🌿 Питомники — {region_label} область</b>\n"]
    for n in nurseries:
        types_str = ", ".join(n["types"])
        lines.append(
            f"🌿 <b>{n['name']}</b>\n"
            f"📍 {n['address']}\n"
            f"📞 {n['phone']}\n"
            f"⭐ Рейтинг {n['rating']}\n"
            f"Типы: {types_str}"
        )
    return "\n\n".join(lines)


def _nursery_map_keyboard(region: str) -> InlineKeyboardMarkup:
    nurseries = NURSERIES.get(region, NURSERIES[DEFAULT_REGION])
    buttons = [
        [InlineKeyboardButton(text=f"🗺 {n['name']}", url=n["url"])]
        for n in nurseries
    ]
    buttons.append([
        InlineKeyboardButton(text="🔄 Сменить регион", callback_data="nurseries_change_region")
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def _detect_region(region_str: str | None) -> str | None:
    if not region_str:
        return None
    r = region_str.lower()
    for key in NURSERIES:
        if key in r:
            return key
    return None


@router.message(Command("nurseries"))
async def cmd_nurseries(message: Message):
    user = await get_or_create_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
    )

    region = _detect_region(getattr(user, "region", None) or (user.get("region") if isinstance(user, dict) else None))

    if region:
        text = _format_nurseries(region)
        keyboard = _nursery_map_keyboard(region)
        await message.answer(text, reply_markup=keyboard, parse_mode="HTML")
    else:
        await message.answer(
            "🌿 <b>Питомники растений</b>\n\nВыберите ваш регион, чтобы показать ближайшие питомники:",
            reply_markup=_region_keyboard(),
            parse_mode="HTML",
        )


@router.callback_query(F.data.startswith("nurseries_region:"))
async def cb_select_region(callback: CallbackQuery):
    region = callback.data.split(":", 1)[1]
    text = _format_nurseries(region)
    keyboard = _nursery_map_keyboard(region)
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "nurseries_change_region")
async def cb_change_region(callback: CallbackQuery):
    await callback.message.edit_text(
        "🌿 <b>Питомники растений</b>\n\nВыберите ваш регион:",
        reply_markup=_region_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()
