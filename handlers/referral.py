"""Хендлер реферальной программы — /referral"""
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton

from config import BOT_USERNAME
from services.database import get_or_create_referral_code, get_referral_stats

router = Router()


@router.message(Command("referral"))
async def cmd_referral(message: Message):
    tid = message.from_user.id
    code = await get_or_create_referral_code(tid)
    stats = await get_referral_stats(tid)

    link = f"https://t.me/{BOT_USERNAME}?start=ref_{code}"
    invited = stats["invited_count"]
    bonus = stats["bonus_messages"]

    text = (
        f"🎁 <b>Реферальная программа</b>\n\n"
        f"Приглашайте друзей — оба получаете по <b>+3 бесплатных сообщения</b> с AI!\n\n"
        f"🔗 <b>Ваша ссылка:</b>\n"
        f"<code>{link}</code>\n\n"
        f"📊 <b>Статистика:</b>\n"
        f"  Приглашено: {invited} чел.\n"
        f"  Бонусных сообщений: {bonus}\n\n"
        f"<i>Поделитесь ссылкой с друзьями — они получат доступ к AI-консультанту по саду,</i>\n"
        f"<i>а вы — дополнительные сообщения для общения с ботом.</i>"
    )

    builder = InlineKeyboardBuilder()
    share_text = f"🌿 Попробуй AI-помощника для сада! Консультации, подбор растений, диагностика болезней.\n{link}"
    builder.row(InlineKeyboardButton(
        text="📤 Поделиться",
        url=f"https://t.me/share/url?url={link}&text={share_text}",
    ))

    await message.answer(text, parse_mode="HTML", reply_markup=builder.as_markup())
