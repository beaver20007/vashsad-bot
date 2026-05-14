"""Хендлер фото-диагностики — с сохранением в PostgreSQL"""
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, PhotoSize

from config import FREE_PHOTO_LIMIT
from keyboards import back_to_menu_keyboard, subscribe_keyboard, cancel_keyboard
from services.database import get_or_create_user, can_use_photo, update_user, save_diagnosis
from services.ai import ask_claude_with_image

router = Router()

PHOTO_PROMPT_TEXT = (
    "📸 <b>Фото-диагностика растений</b>\n\n"
    "Пришлите фото больного или подозрительного растения.\n\n"
    "Для лучшего результата сфотографируйте:\n"
    "• 🍃 Поражённый лист (крупно)\n"
    "• 🌿 Общий вид растения\n"
    "• 🪵 Ствол или стебель (если есть изменения)\n\n"
    "Чем чётче фото — тем точнее диагноз 🔍\n\n"
    "<i>Просто отправьте фото в этот чат ↓</i>"
)


@router.message(Command("photo"))
async def cmd_photo(message: Message):
    user = await get_or_create_user(message.from_user.id)
    if not can_use_photo(user, FREE_PHOTO_LIMIT):
        await message.answer(
            f"⚠️ Лимит бесплатных фото-диагностик исчерпан "
            f"({FREE_PHOTO_LIMIT}/мес).\n\n"
            f"Оформите подписку <b>«Сад Про»</b> — безлимитная диагностика!",
            parse_mode="HTML",
            reply_markup=subscribe_keyboard(),
        )
        return
    await message.answer(PHOTO_PROMPT_TEXT, parse_mode="HTML")


@router.callback_query(F.data == "menu:photo")
async def cb_photo(callback: CallbackQuery):
    user = await get_or_create_user(callback.from_user.id)
    if not can_use_photo(user, FREE_PHOTO_LIMIT):
        await callback.message.edit_text(
            f"⚠️ Лимит бесплатных фото-диагностик исчерпан.\n\n"
            f"Оформите подписку <b>«Сад Про»</b>!",
            parse_mode="HTML",
            reply_markup=subscribe_keyboard(),
        )
        await callback.answer()
        return
    await callback.message.edit_text(
        PHOTO_PROMPT_TEXT, parse_mode="HTML", reply_markup=cancel_keyboard(),
    )
    await callback.answer()


@router.message(F.photo)
async def handle_photo(message: Message):
    user = await get_or_create_user(
        message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
    )

    if not can_use_photo(user, FREE_PHOTO_LIMIT):
        await message.answer(
            f"⚠️ Лимит бесплатных фото-диагностик исчерпан ({FREE_PHOTO_LIMIT}/мес).\n\n"
            f"Оформите подписку <b>«Сад Про»</b>!",
            parse_mode="HTML",
            reply_markup=subscribe_keyboard(),
        )
        return

    processing_msg = await message.answer(
        "🔍 <b>Анализирую ваше растение...</b>\n\n<i>Это займёт несколько секунд.</i>",
        parse_mode="HTML",
    )
    await message.bot.send_chat_action(message.chat.id, "typing")

    photo: PhotoSize = message.photo[-1]
    file = await message.bot.get_file(photo.file_id)
    file_bytes = await message.bot.download_file(file.file_path)

    user_question = message.caption or "Что не так с этим растением? Поставь диагноз."

    result = await ask_claude_with_image(
        image_bytes=file_bytes.read(),
        mime_type="image/jpeg",
        question=user_question,
    )

    # ── Сохраняем диагностику в БД ──
    await save_diagnosis(
        telegram_id=message.from_user.id,
        file_id=photo.file_id,
        question=user_question,
        result=result,
    )

    # Обновляем счётчик
    if not user.is_subscribed:
        user.photo_count += 1
        remaining = FREE_PHOTO_LIMIT - user.photo_count
        await update_user(user)
        footer = f"\n\n<i>Осталось бесплатных диагностик: {remaining}/{FREE_PHOTO_LIMIT}</i>"
    else:
        footer = ""

    await processing_msg.delete()

    await message.answer(
        f"🌿 <b>Результат диагностики:</b>\n\n{result}{footer}",
        parse_mode="HTML",
        reply_markup=back_to_menu_keyboard(),
    )
