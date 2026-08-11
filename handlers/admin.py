"""Хендлер статистики и управления заявками для дизайнера — /stats, /orders"""
import logging
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from config import DESIGNER_TELEGRAM_ID
from services.database import get_designer_stats, get_ab_stats, update_order_status, get_pool

ORDER_STATUSES = {
    "new":        "🆕 Новая",
    "in_progress": "🔄 В работе",
    "review":     "👀 На согласовании",
    "done":       "✅ Выполнена",
    "canceled":   "❌ Отменена",
}

router = Router()
log = logging.getLogger(__name__)


def _only_designer(message: Message) -> bool:
    return message.from_user.id == DESIGNER_TELEGRAM_ID


@router.message(Command("stats"))
async def cmd_stats(message: Message):
    if not _only_designer(message):
        return  # тихо игнорируем для всех остальных

    await message.answer("⏳ Считаю статистику...")
    stats = await get_designer_stats()

    top = "\n".join(
        f"  {i+1}. {s['service_name']} — {s['cnt']} заявок"
        for i, s in enumerate(stats["top_services"])
    ) or "  Нет данных"

    text = (
        f"📊 <b>Статистика ВашСад Бот</b>\n\n"
        f"👥 <b>Пользователи:</b>\n"
        f"  Всего: {stats['total_users']}\n"
        f"  За 7 дней: +{stats['new_7d']}\n"
        f"  За 30 дней: +{stats['new_30d']}\n"
        f"  Подписчиков: {stats['subscribed']} ⭐\n\n"
        f"📋 <b>Заявки:</b>\n"
        f"  Всего: {stats['total_orders']}\n"
        f"  За 7 дней: {stats['orders_7d']}\n\n"
        f"💰 <b>Выручка (оценка):</b> {int(stats['revenue']):,} ₽\n\n"
        f"🏆 <b>Топ услуги:</b>\n{top}"
    )

    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(
        text="📋 Последние 5 заявок",
        callback_data="admin:recent_orders",
    ))

    await message.answer(text, parse_mode="HTML", reply_markup=builder.as_markup())


@router.callback_query(F.data == "admin:recent_orders")
async def cb_recent_orders(callback: CallbackQuery):
    if callback.from_user.id != DESIGNER_TELEGRAM_ID:
        await callback.answer("Нет доступа", show_alert=True)
        return

    stats = await get_designer_stats()
    orders = stats["recent_orders"]
    if not orders:
        await callback.message.answer("Заявок пока нет.")
        await callback.answer()
        return

    lines = []
    for o in orders:
        date = o["created_at"].strftime("%d.%m %H:%M")
        name = o.get("first_name") or "—"
        phone = o.get("phone") or "—"
        svc = o.get("service_name") or "—"
        lines.append(f"• <b>{svc}</b>\n  👤 {name}  📱 {phone}  🕐 {date}")

    await callback.message.answer(
        "📋 <b>Последние заявки:</b>\n\n" + "\n\n".join(lines),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(Command("orders"))
async def cmd_orders(message: Message):
    if not _only_designer(message):
        return
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT o.id, o.service_name, o.status, o.created_at,
                      u.first_name, u.telegram_id
               FROM orders o
               JOIN users u ON u.telegram_id = o.telegram_id
               ORDER BY o.created_at DESC LIMIT 10"""
        )
    if not rows:
        await message.answer("Заявок пока нет.")
        return

    builder = InlineKeyboardBuilder()
    for r in rows:
        status_icon = ORDER_STATUSES.get(r["status"], "❓")[:2]
        date = r["created_at"].strftime("%d.%m")
        label = f"{status_icon} #{r['id']} {(r['service_name'] or '')[:18]} · {r['first_name'] or '?'} · {date}"
        builder.row(InlineKeyboardButton(
            text=label,
            callback_data=f"admin:order:{r['id']}",
        ))

    await message.answer(
        "📋 <b>Последние 10 заявок:</b>",
        parse_mode="HTML",
        reply_markup=builder.as_markup(),
    )


@router.callback_query(F.data.startswith("admin:order:"))
async def cb_order_detail(callback: CallbackQuery):
    if callback.from_user.id != DESIGNER_TELEGRAM_ID:
        await callback.answer("Нет доступа", show_alert=True)
        return

    order_id = int(callback.data.split(":")[-1])
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """SELECT o.*, u.first_name, u.username, u.telegram_id as uid
               FROM orders o JOIN users u ON u.telegram_id = o.telegram_id
               WHERE o.id = $1""",
            order_id,
        )
    if not row:
        await callback.answer("Заявка не найдена", show_alert=True)
        return

    current = ORDER_STATUSES.get(row["status"], "❓")
    text = (
        f"📋 <b>Заявка #{order_id}</b>\n\n"
        f"👤 {row['first_name'] or '—'} (@{row['username'] or '—'})\n"
        f"🛎 Услуга: {row['service_name'] or '—'}\n"
        f"📅 {row['created_at'].strftime('%d.%m.%Y %H:%M')}\n"
        f"📊 Статус: {current}\n\n"
        f"📞 {row['phone'] or '—'} · 📧 {row['email'] or '—'}\n"
        f"💬 {row['wishes'] or '—'}"
    )

    builder = InlineKeyboardBuilder()
    for key, label in ORDER_STATUSES.items():
        if key != row["status"]:
            builder.button(text=label, callback_data=f"admin:setstatus:{order_id}:{key}")
    builder.adjust(2)
    builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="admin:recent_orders"))

    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("admin:setstatus:"))
async def cb_set_status(callback: CallbackQuery, bot: Bot):
    if callback.from_user.id != DESIGNER_TELEGRAM_ID:
        await callback.answer("Нет доступа", show_alert=True)
        return

    parts = callback.data.split(":")
    order_id   = int(parts[2])
    new_status = parts[3]

    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "UPDATE orders SET status=$1 WHERE id=$2 RETURNING telegram_id, service_name",
            new_status, order_id,
        )

    if row:
        label = ORDER_STATUSES.get(new_status, new_status)
        status_texts = {
            "in_progress": "🔄 Ваша заявка <b>принята в работу</b>! Дизайнер уже занимается вашим проектом.",
            "review":      "👀 Ваша заявка <b>на согласовании</b>. Ожидайте обратной связи.",
            "done":        "✅ Ваша заявка <b>выполнена</b>! Свяжитесь с дизайнером для получения результатов.",
            "canceled":    "❌ Ваша заявка <b>отменена</b>. Если есть вопросы — напишите нам.",
        }
        msg_text = status_texts.get(new_status)
        if msg_text:
            try:
                await bot.send_message(
                    row["telegram_id"],
                    f"📋 <b>Обновление по заявке #{order_id}</b>\n\n"
                    f"Услуга: {row['service_name'] or '—'}\n\n"
                    f"{msg_text}",
                    parse_mode="HTML",
                )
            except Exception as e:
                log.warning("Не удалось уведомить пользователя %s: %s", row["telegram_id"], e)

        if new_status == "done":
            from services.scheduler import schedule_nps
            await schedule_nps(bot, row["telegram_id"], order_id)

        await callback.answer(f"Статус → {label}", show_alert=False)
        await cb_order_detail(callback)
    else:
        await callback.answer("Ошибка обновления", show_alert=True)


@router.message(Command("update_order"))
async def cmd_update_order(message: Message):
    if message.from_user.id != DESIGNER_TELEGRAM_ID:
        return
    # Usage: /update_order ORDER_ID STATUS
    parts = message.text.split()
    if len(parts) < 3:
        await message.answer("Использование: /update_order ORDER_ID STATUS\nСтатусы: in_progress, review, done, canceled")
        return
    order_id = parts[1]
    status = parts[2]
    valid_statuses = ["new", "in_progress", "review", "done", "canceled"]
    if status not in valid_statuses:
        await message.answer(f"Неверный статус. Допустимые: {', '.join(valid_statuses)}")
        return

    row = await update_order_status(int(order_id), status)
    if not row:
        await message.answer(f"Заявка #{order_id} не найдена")
        return

    STATUS_LABELS = {
        "new":         "🆕 Новая",
        "in_progress": "🔄 В работе",
        "review":      "👀 На согласовании",
        "done":        "✅ Выполнена",
        "canceled":    "❌ Отменена",
    }
    STATUS_MSGS = {
        "in_progress": "🔄 <b>Ваша заявка принята в работу!</b>\n\nДизайнер приступил к работе над вашим проектом.",
        "review":      "👀 <b>Проект на согласовании</b>\n\nМы подготовили материалы. Свяжемся с вами.",
        "done":        "✅ <b>Проект выполнен!</b>\n\nОставьте отзыв в приложении 🌿",
        "canceled":    "❌ <b>Заявка отменена.</b>\n\nЕсли есть вопросы — напишите нам.",
    }
    service_label = row.get("service_name") or row.get("service_type") or "Заявка"
    user_msg = STATUS_MSGS.get(status)
    notified = False
    if user_msg and row["telegram_id"]:
        try:
            await message.bot.send_message(
                row["telegram_id"],
                f"📋 <b>Обновление по заявке #{order_id}</b>\n"
                f"Услуга: {service_label}\n\n"
                f"{user_msg}",
                parse_mode="HTML",
            )
            notified = True
        except Exception as e:
            log.warning("Не удалось уведомить пользователя %s: %s", row["telegram_id"], e)
    label = STATUS_LABELS.get(status, status)
    note = "Пользователь уведомлён" if notified else "Уведомление не отправлено (нет сообщения для этого статуса)"
    await message.answer(f"✅ Заявка #{order_id} обновлена\nСтатус: {label}\n{note}")


# ---------------------------------------------------------------------------
# /broadcast — рассылка всем пользователям (только дизайнер)
# ---------------------------------------------------------------------------

_pending_broadcasts: dict[int, str] = {}


@router.message(Command("broadcast"))
async def cmd_broadcast(message: Message):
    if not _only_designer(message):
        return

    text = message.text.removeprefix("/broadcast").strip()
    if not text:
        await message.answer("Использование: /broadcast Текст сообщения")
        return

    pool = await get_pool()
    async with pool.acquire() as conn:
        count = await conn.fetchval("SELECT COUNT(*) FROM users WHERE is_banned IS NOT TRUE")

    keyboard = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=f"✅ Разослать {count} пользователям", callback_data="broadcast:confirm"),
        InlineKeyboardButton(text="❌ Отмена", callback_data="broadcast:cancel"),
    ]])

    _pending_broadcasts[message.from_user.id] = text

    await message.answer(
        f"📣 <b>Превью рассылки:</b>\n\n{text}\n\n"
        f"👥 Получателей: {count}\n\nПодтвердить?",
        reply_markup=keyboard,
        parse_mode="HTML",
    )


@router.callback_query(F.data == "broadcast:confirm")
async def cb_broadcast_confirm(callback: CallbackQuery):
    if callback.from_user.id != DESIGNER_TELEGRAM_ID:
        await callback.answer()
        return

    text = _pending_broadcasts.pop(callback.from_user.id, None)
    if not text:
        await callback.answer("Рассылка устарела", show_alert=True)
        return

    await callback.message.edit_text("📣 Рассылка запущена...")
    await callback.answer()

    pool = await get_pool()
    async with pool.acquire() as conn:
        users = await conn.fetch("SELECT telegram_id FROM users WHERE is_banned IS NOT TRUE")

    sent = 0
    failed = 0
    for row in users:
        try:
            await callback.bot.send_message(row["telegram_id"], text, parse_mode="HTML")
            sent += 1
        except Exception:
            failed += 1

    await callback.message.edit_text(
        f"✅ Рассылка завершена\n📤 Отправлено: {sent}\n❌ Ошибок: {failed}"
    )


@router.callback_query(F.data == "broadcast:cancel")
async def cb_broadcast_cancel(callback: CallbackQuery):
    _pending_broadcasts.pop(callback.from_user.id, None)
    await callback.message.edit_text("❌ Рассылка отменена")
    await callback.answer()


# ---------------------------------------------------------------------------
# /ab_stats — статистика A/B теста приветствия (только дизайнер)
# ---------------------------------------------------------------------------

@router.message(Command("ab_stats"))
async def cmd_ab_stats(message: Message):
    if not _only_designer(message):
        return

    rows = await get_ab_stats()
    if not rows:
        await message.answer("Данных A/B теста пока нет.")
        return

    lines = ["📊 <b>A/B тест приветствия</b>\n"]
    for r in rows:
        variant = r["variant"] or "?"
        starts = r["starts"] or 0
        orders = r["orders"] or 0
        conv = f"{orders / starts * 100:.1f}%" if starts else "—"
        lines.append(
            f"<b>Вариант {variant}:</b>\n"
            f"  Визиты /start: {starts}\n"
            f"  Заказы: {orders}\n"
            f"  Конверсия: {conv}"
        )

    await message.answer("\n\n".join(lines), parse_mode="HTML")


# ---------------------------------------------------------------------------
# /broadcast_segment — сегментированная рассылка (только дизайнер)
# ---------------------------------------------------------------------------

_pending_segments: dict[int, dict] = {}


@router.message(Command("broadcast_segment"))
async def cmd_broadcast_segment(message: Message):
    if message.from_user.id != DESIGNER_TELEGRAM_ID:
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⭐ Только подписчики", callback_data="bseg:subscribed")],
        [InlineKeyboardButton(text="🌟 Подписчики Stars", callback_data="bseg:stars_subscribers")],
        [InlineKeyboardButton(text="📋 Есть заявки", callback_data="bseg:with_orders")],
        [InlineKeyboardButton(text="📍 Нижегородская область", callback_data="bseg:region_нижегородская")],
        [InlineKeyboardButton(text="📍 Владимирская область", callback_data="bseg:region_владимирская")],
        [InlineKeyboardButton(text="📍 Московская область", callback_data="bseg:region_московская")],
        [InlineKeyboardButton(text="🆕 Новые (7 дней)", callback_data="bseg:new_7d")],
        [InlineKeyboardButton(text="😴 Неактивные (30 дней)", callback_data="bseg:inactive_30d")],
        [InlineKeyboardButton(text="👥 Все пользователи", callback_data="bseg:all")],
    ])
    await message.answer("📣 Выберите сегмент рассылки:", reply_markup=keyboard)
    _pending_segments[message.from_user.id] = {'step': 'choose_segment'}


@router.callback_query(F.data.startswith("bseg:"))
async def cb_segment_chosen(callback: CallbackQuery):
    if callback.from_user.id != DESIGNER_TELEGRAM_ID:
        await callback.answer()
        return

    segment = callback.data.split(":", 1)[1]
    _pending_segments[callback.from_user.id] = {'segment': segment, 'step': 'await_text'}

    segment_labels = {
        'subscribed': 'подписчики',
        'stars_subscribers': 'подписчики Stars (активная подписка)',
        'with_orders': 'пользователи с заявками',
        'region_нижегородская': 'Нижегородская обл.',
        'region_владимирская': 'Владимирская обл.',
        'region_московская': 'Московская обл.',
        'new_7d': 'новые за 7 дней',
        'inactive_30d': 'неактивные 30 дней',
        'all': 'все пользователи',
    }
    label = segment_labels.get(segment, segment)
    await callback.message.edit_text(
        f"📣 Сегмент: <b>{label}</b>\n\nОтправьте текст рассылки следующим сообщением:",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(lambda msg: msg.from_user.id == DESIGNER_TELEGRAM_ID and msg.from_user.id in _pending_segments and _pending_segments.get(msg.from_user.id, {}).get('step') == 'await_text')
async def receive_segment_text(message: Message):
    data = _pending_segments.get(message.from_user.id, {})
    segment = data.get('segment', 'all')
    text = message.text or ''
    if not text:
        return

    pool = await get_pool()
    async with pool.acquire() as conn:
        if segment == 'subscribed':
            users = await conn.fetch("SELECT telegram_id FROM users WHERE is_subscribed = TRUE AND (is_banned IS NOT TRUE)")
        elif segment == 'stars_subscribers':
            users = await conn.fetch(
                "SELECT telegram_id FROM users WHERE subscription_expires_at > NOW() AND (is_banned IS NOT TRUE)"
            )
        elif segment == 'with_orders':
            users = await conn.fetch(
                """SELECT DISTINCT u.telegram_id FROM users u
                   JOIN orders o ON o.telegram_id = u.telegram_id
                   WHERE (u.is_banned IS NOT TRUE)"""
            )
        elif segment.startswith('region_'):
            region = segment.replace('region_', '')
            users = await conn.fetch("SELECT telegram_id FROM users WHERE region ILIKE $1 AND (is_banned IS NOT TRUE)", f"%{region}%")
        elif segment == 'new_7d':
            users = await conn.fetch("SELECT telegram_id FROM users WHERE created_at > NOW() - INTERVAL '7 days' AND (is_banned IS NOT TRUE)")
        elif segment == 'inactive_30d':
            # last_activity column may not exist — fall back to created_at + zero chat_count
            has_last_activity = await conn.fetchval(
                """SELECT COUNT(*) FROM information_schema.columns
                   WHERE table_name='users' AND column_name='last_activity'"""
            )
            if has_last_activity:
                users = await conn.fetch(
                    """SELECT telegram_id FROM users
                       WHERE last_activity < NOW() - INTERVAL '30 days'
                       AND (is_banned IS NOT TRUE)"""
                )
            else:
                users = await conn.fetch(
                    """SELECT telegram_id FROM users
                       WHERE created_at < NOW() - INTERVAL '30 days'
                       AND chat_count = 0
                       AND (is_banned IS NOT TRUE)"""
                )
        else:
            users = await conn.fetch("SELECT telegram_id FROM users WHERE is_banned IS NOT TRUE")

    del _pending_segments[message.from_user.id]

    await message.answer(f"📣 Рассылаю {len(users)} пользователям...")
    sent, failed = 0, 0
    for row in users:
        try:
            await message.bot.send_message(row['telegram_id'], text, parse_mode="HTML")
            sent += 1
        except Exception:
            failed += 1

    await message.answer(f"✅ Готово! Отправлено: {sent}, ошибок: {failed}")
