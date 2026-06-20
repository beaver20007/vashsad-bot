"""
handlers/saved_replies.py
Шаблоны быстрых ответов для дизайнера.

Команды (только для DESIGNER_TELEGRAM_ID):
  /save_reply ALIAS текст...   — сохранить шаблон
  /replies                     — показать список шаблонов
  /r ALIAS                     — отправить шаблон
  /reply ALIAS                 — то же самое
  /delete_reply ALIAS          — удалить шаблон
"""

import logging
import os

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from services.database import get_pool

log = logging.getLogger(__name__)
router = Router()

# ── Вспомогательные функции БД ──────────────────────────────────────────────

async def _ensure_table() -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS saved_replies (
                id          SERIAL PRIMARY KEY,
                telegram_id BIGINT NOT NULL,
                alias       VARCHAR(50) NOT NULL,
                text        TEXT NOT NULL,
                created_at  TIMESTAMP DEFAULT NOW(),
                UNIQUE (telegram_id, alias)
            )
        """)


async def _save_reply(telegram_id: int, alias: str, text: str) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO saved_replies (telegram_id, alias, text)
               VALUES ($1, $2, $3)
               ON CONFLICT (telegram_id, alias) DO UPDATE SET text=$3, created_at=NOW()""",
            telegram_id, alias, text,
        )


async def _get_reply(telegram_id: int, alias: str) -> str | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval(
            "SELECT text FROM saved_replies WHERE telegram_id=$1 AND alias=$2",
            telegram_id, alias,
        )


async def _list_replies(telegram_id: int) -> list[str]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT alias FROM saved_replies WHERE telegram_id=$1 ORDER BY alias",
            telegram_id,
        )
    return [r["alias"] for r in rows]


async def _delete_reply(telegram_id: int, alias: str) -> bool:
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            "DELETE FROM saved_replies WHERE telegram_id=$1 AND alias=$2",
            telegram_id, alias,
        )
    return result.endswith("1")


# ── Проверка прав ────────────────────────────────────────────────────────────

def _is_designer(telegram_id: int) -> bool:
    designer_id = os.getenv("DESIGNER_TELEGRAM_ID", "")
    try:
        return int(designer_id) == telegram_id
    except (ValueError, TypeError):
        return False


# ── Хэндлеры ────────────────────────────────────────────────────────────────

@router.message(Command("save_reply"))
async def cmd_save_reply(message: Message) -> None:
    if not _is_designer(message.from_user.id):
        return

    await _ensure_table()

    # /save_reply ALIAS текст...
    parts = (message.text or "").split(maxsplit=2)
    if len(parts) < 3:
        await message.answer(
            "Использование: <code>/save_reply ALIAS текст шаблона</code>\n"
            "Пример: <code>/save_reply hello Здравствуйте! Рада вас видеть.</code>",
            parse_mode="HTML",
        )
        return

    alias = parts[1].lower()
    text = parts[2]

    if len(alias) > 50:
        await message.answer("Псевдоним не должен превышать 50 символов.")
        return

    await _save_reply(message.from_user.id, alias, text)
    await message.answer(f"Шаблон <b>{alias}</b> сохранён.", parse_mode="HTML")


@router.message(Command("replies"))
async def cmd_replies(message: Message) -> None:
    if not _is_designer(message.from_user.id):
        return

    await _ensure_table()

    aliases = await _list_replies(message.from_user.id)
    if not aliases:
        await message.answer("Сохранённых шаблонов пока нет.\nДобавьте: /save_reply ALIAS текст")
        return

    # Кнопки: один ряд — одна кнопка с /r ALIAS
    buttons = [
        [InlineKeyboardButton(text=f"/r {a}", switch_inline_query_current_chat=f"/r {a}")]
        for a in aliases
    ]
    # switch_inline_query_current_chat вставляет текст в поле ввода —
    # но здесь нам нужно просто показать список. Используем callback_data
    # с префиксом "sr:" чтобы можно было нажать и бот отправил шаблон.
    buttons = [
        [InlineKeyboardButton(text=f"📨 {a}", callback_data=f"sr_send:{a}")]
        for a in aliases
    ]
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.answer(
        f"Сохранённые шаблоны ({len(aliases)}):\nНажмите кнопку — бот отправит текст.",
        reply_markup=keyboard,
    )


@router.message(Command("r", "reply"))
async def cmd_r(message: Message) -> None:
    if not _is_designer(message.from_user.id):
        return

    await _ensure_table()

    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Использование: <code>/r ALIAS</code>", parse_mode="HTML")
        return

    alias = parts[1].strip().lower()
    text = await _get_reply(message.from_user.id, alias)
    if text is None:
        await message.answer(
            f"Шаблон <b>{alias}</b> не найден. Посмотрите список: /replies",
            parse_mode="HTML",
        )
        return

    await message.answer(text)


@router.message(Command("delete_reply"))
async def cmd_delete_reply(message: Message) -> None:
    if not _is_designer(message.from_user.id):
        return

    await _ensure_table()

    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Использование: <code>/delete_reply ALIAS</code>", parse_mode="HTML")
        return

    alias = parts[1].strip().lower()
    deleted = await _delete_reply(message.from_user.id, alias)
    if deleted:
        await message.answer(f"Шаблон <b>{alias}</b> удалён.", parse_mode="HTML")
    else:
        await message.answer(
            f"Шаблон <b>{alias}</b> не найден.",
            parse_mode="HTML",
        )


# ── Callback: кнопка «отправить шаблон» из /replies ─────────────────────────

from aiogram.types import CallbackQuery


@router.callback_query(lambda c: c.data and c.data.startswith("sr_send:"))
async def cb_send_reply(callback: CallbackQuery) -> None:
    if not _is_designer(callback.from_user.id):
        await callback.answer("Нет прав.", show_alert=True)
        return

    alias = callback.data.split(":", 1)[1]
    text = await _get_reply(callback.from_user.id, alias)
    if text is None:
        await callback.answer(f"Шаблон '{alias}' не найден.", show_alert=True)
        return

    await callback.message.answer(text)
    await callback.answer()
