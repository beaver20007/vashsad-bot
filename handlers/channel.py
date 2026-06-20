"""Хендлер проверки подписки на Telegram-канал"""
import logging

from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from config import CHANNEL_USERNAME
from services.database import get_or_create_user, add_bonus_messages

log = logging.getLogger(__name__)
router = Router()

BONUS_AMOUNT = 5


def _subscribe_keyboard() -> InlineKeyboardMarkup:
    channel = CHANNEL_USERNAME if CHANNEL_USERNAME.startswith("@") else f"@{CHANNEL_USERNAME}"
    channel_link = channel.lstrip("@")
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="📢 Подписаться на канал",
                url=f"https://t.me/{channel_link}",
            )
        ],
        [
            InlineKeyboardButton(
                text="✅ Проверить подписку",
                callback_data="channel:check",
            )
        ],
    ])


async def check_subscription(user_id: int, bot: Bot) -> bool:
    """Проверить, подписан ли пользователь на CHANNEL_USERNAME."""
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_USERNAME, user_id=user_id)
        return member.status in ("member", "administrator", "creator")
    except Exception as e:
        log.warning("check_subscription error for user %s: %s", user_id, e)
        return False


@router.message(Command("subscribe_channel"))
async def cmd_subscribe_channel(message: Message):
    channel = CHANNEL_USERNAME if CHANNEL_USERNAME.startswith("@") else f"@{CHANNEL_USERNAME}"
    await message.answer(
        f"📢 <b>Подпишитесь на наш канал {channel}</b>\n\n"
        f"Там мы публикуем:\n"
        f"• Советы по уходу за садом\n"
        f"• Идеи ландшафтного дизайна\n"
        f"• Сезонные напоминания\n\n"
        f"🎁 За подписку вы получите <b>+{BONUS_AMOUNT} бесплатных сообщений</b> к AI-чату!",
        parse_mode="HTML",
        reply_markup=_subscribe_keyboard(),
    )


@router.callback_query(F.data == "channel:check")
async def cb_check_subscription(callback: CallbackQuery):
    user_id = callback.from_user.id
    subscribed = await check_subscription(user_id, callback.bot)

    if subscribed:
        # Проверяем, не начислялся ли бонус уже (через БД)
        user = await get_or_create_user(
            user_id,
            username=callback.from_user.username,
            first_name=callback.from_user.first_name,
        )
        # Начисляем бонус
        await add_bonus_messages(user_id, BONUS_AMOUNT)
        channel = CHANNEL_USERNAME if CHANNEL_USERNAME.startswith("@") else f"@{CHANNEL_USERNAME}"
        await callback.message.edit_text(
            f"✅ <b>Спасибо за подписку на {channel}!</b>\n\n"
            f"Вам начислено <b>+{BONUS_AMOUNT} бонусных сообщений</b> для AI-чата. 🌿\n\n"
            f"Продолжайте задавать вопросы — я здесь, чтобы помочь!",
            parse_mode="HTML",
        )
    else:
        channel = CHANNEL_USERNAME if CHANNEL_USERNAME.startswith("@") else f"@{CHANNEL_USERNAME}"
        await callback.message.edit_text(
            f"❌ <b>Подписка не обнаружена</b>\n\n"
            f"Пожалуйста, подпишитесь на канал {channel}, а затем нажмите «Проверить подписку» снова.",
            parse_mode="HTML",
            reply_markup=_subscribe_keyboard(),
        )

    await callback.answer()
