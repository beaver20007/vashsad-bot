"""Команды для отдельного админ-бота — доступ по таблице admin_users, не по DESIGNER_TELEGRAM_ID.

Перенесено (не дублировано) из handlers/admin.py и handlers/moderation.py основного бота
(трек scaffold-admin-bot). Оригиналы там удалены — см. docs/AGENTS.md.
"""
import logging

from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from services.database import get_designer_stats, get_ab_stats, update_order_status, get_pool
from services.admin_auth import (
    is_admin, is_owner, admin_table_empty, add_admin, list_admins,
)

router = Router()
log = logging.getLogger(__name__)

ORDER_STATUSES = {
    "new":        "🆕 Новая",
    "in_progress": "🔄 В работе",
    "review":     "👀 На согласовании",
    "done":       "✅ Выполнена",
    "canceled":   "❌ Отменена",
}

# Фильтры /orders. "Отвечено" — не статус заявки (тот остаётся клиентским
# жизненным циклом new/in_progress/review/done/canceled), а отдельный флаг
# orders.replied ("хоть раз ответили клиенту"), исключая уже закрытые —
# закрытая заявка с ответом показывается в "Закрыто", не дублируется.
ORDER_FILTERS: dict[str, tuple[str, str | None]] = {
    "all":         ("Все",        None),
    "new":         ("🆕 Новые",    "o.status = 'new'"),
    "in_progress": ("🔄 В работе", "o.status = 'in_progress'"),
    "replied":     ("💬 Отвечено", "o.replied = TRUE AND o.status NOT IN ('done','canceled')"),
    "closed":      ("✅ Закрыто",  "o.status IN ('done','canceled')"),
}

# Ожидание текста ответа клиенту: admin_id -> {order_id, client_id, order_label}
_pending_replies: dict[int, dict] = {}


# ---------------------------------------------------------------------------
# /start — bootstrap: первый /start от пустой таблицы становится owner
# ---------------------------------------------------------------------------

@router.message(Command("start"))
async def cmd_start(message: Message):
    uid = message.from_user.id
    if await is_admin(uid):
        role = await get_admin_role_safe(uid)
        await message.answer(
            f"👋 Снова здравствуйте! Ваша роль: <b>{role}</b>.\n\n"
            "Команды: /stats /orders /broadcast /broadcast_segment /ab_stats "
            "/ban /unban /whitelist /bans /reset_onboarding /add_admin",
            parse_mode="HTML",
        )
        return

    if await admin_table_empty():
        name = message.from_user.full_name or message.from_user.first_name or "Owner"
        await add_admin(uid, name, "owner")
        await message.answer(
            "🌿 <b>Админ-бот ВашСад</b>\n\n"
            f"Вы первый, кто сюда написал — назначены <b>owner</b>.\n"
            "Добавляйте остальных: <code>/add_admin ID Имя role</code> "
            "(role: owner/team).",
            parse_mode="HTML",
        )
        return

    await message.answer("⛔ Нет доступа. Обратитесь к владельцу бота.")


async def get_admin_role_safe(telegram_id: int) -> str:
    from services.admin_auth import get_admin_role
    return await get_admin_role(telegram_id) or "team"


# ---------------------------------------------------------------------------
# /add_admin — только owner
# ---------------------------------------------------------------------------

@router.message(Command("add_admin"))
async def cmd_add_admin(message: Message):
    if not await is_owner(message.from_user.id):
        return
    parts = message.text.split(maxsplit=3)
    if len(parts) < 4 or parts[3] not in ("owner", "team"):
        await message.answer(
            "Формат: <code>/add_admin ID Имя role</code>\nrole: owner | team",
            parse_mode="HTML",
        )
        return
    try:
        target_id = int(parts[1])
    except ValueError:
        await message.answer("ID должен быть числом.")
        return
    name, role = parts[2], parts[3]
    await add_admin(target_id, name, role)
    await message.answer(f"✅ {name} ({target_id}) добавлен(а) как <b>{role}</b>.", parse_mode="HTML")


@router.message(Command("admins"))
async def cmd_admins(message: Message):
    if not await is_admin(message.from_user.id):
        return
    admins = await list_admins()
    if not admins:
        await message.answer("Список администраторов пуст.")
        return
    lines = [f"{'👑' if a['role'] == 'owner' else '👤'} {a['name'] or '—'} · {a['telegram_id']} · {a['role']}" for a in admins]
    await message.answer("<b>Администраторы:</b>\n\n" + "\n".join(lines), parse_mode="HTML")


# ---------------------------------------------------------------------------
# /stats — перенесено из handlers/admin.py (было: DESIGNER_TELEGRAM_ID)
# ---------------------------------------------------------------------------

@router.message(Command("stats"))
async def cmd_stats(message: Message):
    if not await is_admin(message.from_user.id):
        return

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
    if not await is_admin(callback.from_user.id):
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


# ---------------------------------------------------------------------------
# /orders — список с фильтром по статусу, детали, смена статуса, «Ответить»
# (перенесено из handlers/admin.py + трек admin-bot-layer-a-workflow)
# ---------------------------------------------------------------------------

def _orders_filter_keyboard(active: str) -> list[list[InlineKeyboardButton]]:
    row1, row2 = [], []
    for i, (key, (label, _)) in enumerate(ORDER_FILTERS.items()):
        text = f"• {label} •" if key == active else label
        btn = InlineKeyboardButton(text=text, callback_data=f"admin:orders:{key}")
        (row1 if i < 3 else row2).append(btn)
    return [row1, row2]


async def _render_orders_list(filter_key: str) -> tuple[str, InlineKeyboardMarkup]:
    label, condition = ORDER_FILTERS.get(filter_key, ORDER_FILTERS["all"])
    where = f"WHERE {condition}" if condition else ""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"""SELECT o.id, o.service_name, o.status, o.created_at,
                       u.first_name, u.telegram_id
                FROM orders o
                JOIN users u ON u.telegram_id = o.telegram_id
                {where}
                ORDER BY o.created_at DESC LIMIT 10"""
        )

    builder = InlineKeyboardBuilder()
    for r in rows:
        status_icon = ORDER_STATUSES.get(r["status"], "❓")[:2]
        date = r["created_at"].strftime("%d.%m")
        item_label = f"{status_icon} #{r['id']} {(r['service_name'] or '')[:18]} · {r['first_name'] or '?'} · {date}"
        builder.row(InlineKeyboardButton(
            text=item_label,
            callback_data=f"admin:order:{r['id']}:{filter_key}",
        ))
    for row in _orders_filter_keyboard(filter_key):
        builder.row(*row)

    text = f"📋 <b>Заявки — {label}</b>" if rows else f"📋 <b>Заявки — {label}</b>\n\nНичего не найдено."
    return text, builder.as_markup()


@router.message(Command("orders"))
async def cmd_orders(message: Message):
    if not await is_admin(message.from_user.id):
        return
    text, markup = await _render_orders_list("all")
    await message.answer(text, parse_mode="HTML", reply_markup=markup)


@router.callback_query(F.data.startswith("admin:orders:"))
async def cb_orders_filter(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    filter_key = callback.data.split(":")[2]
    text, markup = await _render_orders_list(filter_key)
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=markup)
    await callback.answer()


async def _render_order_detail(order_id: int, filter_key: str) -> tuple[str, InlineKeyboardMarkup] | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """SELECT o.*, u.first_name, u.username, u.telegram_id as uid
               FROM orders o JOIN users u ON u.telegram_id = o.telegram_id
               WHERE o.id = $1""",
            order_id,
        )
    if not row:
        return None

    current = ORDER_STATUSES.get(row["status"], "❓")
    replied_line = "\n💬 Клиенту уже отвечали" if row.get("replied") else ""
    text = (
        f"📋 <b>Заявка #{order_id}</b>\n\n"
        f"👤 {row['first_name'] or '—'} (@{row['username'] or '—'})\n"
        f"🛎 Услуга: {row['service_name'] or '—'}\n"
        f"📅 {row['created_at'].strftime('%d.%m.%Y %H:%M')}\n"
        f"📊 Статус: {current}{replied_line}\n\n"
        f"📞 {row['phone'] or '—'} · 📧 {row['email'] or '—'}\n"
        f"💬 {row['wishes'] or '—'}"
    )

    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(
        text="✉️ Ответить клиенту",
        callback_data=f"admin:reply:{order_id}:{filter_key}",
    ))
    for key, label in ORDER_STATUSES.items():
        if key != row["status"]:
            builder.button(text=label, callback_data=f"admin:setstatus:{order_id}:{key}:{filter_key}")
    builder.adjust(1, 2)
    builder.row(InlineKeyboardButton(text="◀️ К списку", callback_data=f"admin:orders:{filter_key}"))

    return text, builder.as_markup()


@router.callback_query(F.data.startswith("admin:order:"))
async def cb_order_detail(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return

    parts = callback.data.split(":")
    order_id = int(parts[2])
    filter_key = parts[3] if len(parts) > 3 else "all"

    rendered = await _render_order_detail(order_id, filter_key)
    if not rendered:
        await callback.answer("Заявка не найдена", show_alert=True)
        return
    text, markup = rendered
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=markup)
    await callback.answer()


@router.callback_query(F.data.startswith("admin:setstatus:"))
async def cb_set_status(callback: CallbackQuery, main_bot: Bot):
    if not await is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return

    parts = callback.data.split(":")
    order_id   = int(parts[2])
    new_status = parts[3]
    filter_key = parts[4] if len(parts) > 4 else "all"

    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "UPDATE orders SET status=$1 WHERE id=$2 RETURNING telegram_id, service_name",
            new_status, order_id,
        )

    if not row:
        await callback.answer("Ошибка обновления", show_alert=True)
        return

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
            # main_bot, не bot: клиент переписывается с основным ботом
            # (TELEGRAM_BOT_TOKEN), не с этим админ-ботом — см. admin_bot.py.
            await main_bot.send_message(
                row["telegram_id"],
                f"📋 <b>Обновление по заявке #{order_id}</b>\n\n"
                f"Услуга: {row['service_name'] or '—'}\n\n"
                f"{msg_text}",
                parse_mode="HTML",
            )
        except Exception as e:
            log.warning("Не удалось уведомить пользователя %s: %s", row["telegram_id"], e)

    await callback.answer(f"Статус → {label}", show_alert=False)
    rendered = await _render_order_detail(order_id, filter_key)
    if rendered:
        text, markup = rendered
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=markup)


# ---------------------------------------------------------------------------
# «Ответить клиенту» — свободный текст уходит клиенту через main_bot
# (трек admin-bot-layer-a-workflow)
# ---------------------------------------------------------------------------

@router.callback_query(F.data.startswith("admin:reply:"))
async def cb_reply_start(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return

    parts = callback.data.split(":")
    order_id = int(parts[2])
    filter_key = parts[3] if len(parts) > 3 else "all"

    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """SELECT o.telegram_id, o.service_name, u.first_name
               FROM orders o JOIN users u ON u.telegram_id = o.telegram_id
               WHERE o.id = $1""",
            order_id,
        )
    if not row:
        await callback.answer("Заявка не найдена", show_alert=True)
        return

    _pending_replies[callback.from_user.id] = {
        "order_id": order_id,
        "client_id": row["telegram_id"],
        "filter_key": filter_key,
    }
    await callback.message.answer(
        f"✉️ Ответ клиенту по заявке #{order_id} ({row['first_name'] or '—'}, "
        f"{row['service_name'] or 'услуга'}).\n\n"
        f"Следующим сообщением отправьте текст — он уйдёт клиенту от имени бота "
        f"ВашСад. Отмена: /cancel_reply",
    )
    await callback.answer()


@router.message(Command("cancel_reply"))
async def cmd_cancel_reply(message: Message):
    if _pending_replies.pop(message.from_user.id, None):
        await message.answer("❌ Ответ отменён.")


@router.message(lambda msg: msg.from_user.id in _pending_replies and not (msg.text or "").startswith("/"))
async def receive_reply_text(message: Message, main_bot: Bot):
    if not await is_admin(message.from_user.id):
        return
    pending = _pending_replies.get(message.from_user.id)
    if not pending:
        return
    text = message.text or message.caption
    if not text:
        await message.answer("Поддерживается только текст. Отправьте текстовое сообщение или /cancel_reply.")
        return

    order_id = pending["order_id"]
    client_id = pending["client_id"]
    filter_key = pending["filter_key"]

    try:
        await main_bot.send_message(
            client_id,
            f"💬 <b>Сообщение от дизайнера ВашСад</b> (по заявке #{order_id}):\n\n{text}",
            parse_mode="HTML",
        )
    except Exception as e:
        log.warning("Не удалось отправить ответ клиенту %s: %s", client_id, e)
        await message.answer(f"❌ Не доставлено клиенту: {e}")
        return

    del _pending_replies[message.from_user.id]

    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("UPDATE orders SET replied=TRUE WHERE id=$1", order_id)

    await message.answer("✅ Отправлено клиенту.")
    rendered = await _render_order_detail(order_id, filter_key)
    if rendered:
        detail_text, markup = rendered
        await message.answer(detail_text, parse_mode="HTML", reply_markup=markup)


@router.message(Command("update_order"))
async def cmd_update_order(message: Message, main_bot: Bot):
    if not await is_admin(message.from_user.id):
        return
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
            # main_bot: клиент переписывается с основным ботом, не с этим.
            await main_bot.send_message(
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
# /broadcast — перенесено из handlers/admin.py
# ---------------------------------------------------------------------------

_pending_broadcasts: dict[int, str] = {}


@router.message(Command("broadcast"))
async def cmd_broadcast(message: Message):
    if not await is_admin(message.from_user.id):
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
async def cb_broadcast_confirm(callback: CallbackQuery, main_bot: Bot):
    if not await is_admin(callback.from_user.id):
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
            # main_bot: рассылка клиентам, не с этим админ-ботом.
            await main_bot.send_message(row["telegram_id"], text, parse_mode="HTML")
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
# /ab_stats — перенесено из handlers/admin.py
# ---------------------------------------------------------------------------

@router.message(Command("ab_stats"))
async def cmd_ab_stats(message: Message):
    if not await is_admin(message.from_user.id):
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
# /broadcast_segment — перенесено из handlers/admin.py
# ---------------------------------------------------------------------------

_pending_segments: dict[int, dict] = {}


@router.message(Command("broadcast_segment"))
async def cmd_broadcast_segment(message: Message):
    if not await is_admin(message.from_user.id):
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
    if not await is_admin(callback.from_user.id):
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


@router.message(lambda msg: msg.from_user.id in _pending_segments and _pending_segments.get(msg.from_user.id, {}).get('step') == 'await_text')
async def receive_segment_text(message: Message, main_bot: Bot):
    if not await is_admin(message.from_user.id):
        return
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
            # main_bot: рассылка клиентам, не с этим админ-ботом.
            await main_bot.send_message(row['telegram_id'], text, parse_mode="HTML")
            sent += 1
        except Exception:
            failed += 1

    await message.answer(f"✅ Готово! Отправлено: {sent}, ошибок: {failed}")


# ---------------------------------------------------------------------------
# Модерация — перенесено из handlers/moderation.py
# ---------------------------------------------------------------------------

@router.message(Command("ban"))
async def cmd_ban(message: Message):
    if not await is_admin(message.from_user.id):
        return
    parts = message.text.split(maxsplit=2)
    if len(parts) < 2:
        await message.answer("Формат: <code>/ban USER_ID [причина]</code>", parse_mode="HTML")
        return
    try:
        target_id = int(parts[1])
    except ValueError:
        await message.answer("USER_ID должен быть числом.")
        return
    reason = parts[2] if len(parts) > 2 else "нет причины"

    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET is_banned=TRUE WHERE telegram_id=$1", target_id
        )
        await conn.execute(
            "INSERT INTO ban_log (telegram_id, action, reason, by_admin) VALUES ($1,'ban',$2,$3)",
            target_id, reason, message.from_user.id,
        )
    await message.answer(f"🚫 Пользователь {target_id} заблокирован. Причина: {reason}")


@router.message(Command("unban"))
async def cmd_unban(message: Message):
    if not await is_admin(message.from_user.id):
        return
    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("Формат: <code>/unban USER_ID</code>", parse_mode="HTML")
        return
    try:
        target_id = int(parts[1])
    except ValueError:
        await message.answer("USER_ID должен быть числом.")
        return

    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET is_banned=FALSE WHERE telegram_id=$1", target_id
        )
        await conn.execute(
            "INSERT INTO ban_log (telegram_id, action, by_admin) VALUES ($1,'unban',$2)",
            target_id, message.from_user.id,
        )
    await message.answer(f"✅ Пользователь {target_id} разблокирован.")


@router.message(Command("whitelist"))
async def cmd_whitelist(message: Message):
    if not await is_admin(message.from_user.id):
        return
    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("Формат: <code>/whitelist USER_ID</code>", parse_mode="HTML")
        return
    try:
        target_id = int(parts[1])
    except ValueError:
        await message.answer("USER_ID должен быть числом.")
        return

    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET is_whitelist=TRUE WHERE telegram_id=$1", target_id
        )
        await conn.execute(
            "INSERT INTO ban_log (telegram_id, action, by_admin) VALUES ($1,'whitelist',$2)",
            target_id, message.from_user.id,
        )
    await message.answer(f"⭐ Пользователь {target_id} добавлен в whitelist.")


@router.message(Command("bans"))
async def cmd_bans(message: Message):
    if not await is_admin(message.from_user.id):
        return
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT u.telegram_id, u.first_name, u.username, u.is_banned, u.is_whitelist
               FROM users u WHERE u.is_banned=TRUE OR u.is_whitelist=TRUE
               ORDER BY u.created_at DESC LIMIT 20"""
        )
    if not rows:
        await message.answer("Нет заблокированных или whitelist-пользователей.")
        return
    lines = []
    for r in rows:
        status = "🚫" if r["is_banned"] else "⭐"
        lines.append(f"{status} {r['first_name'] or '—'} (@{r['username'] or '—'}) · {r['telegram_id']}")
    await message.answer(
        "<b>Пользователи с особым статусом:</b>\n\n" + "\n".join(lines),
        parse_mode="HTML",
    )


# ---------------------------------------------------------------------------
# /reset_onboarding — новая команда, раньше не существовала нигде в коде
# ---------------------------------------------------------------------------

@router.message(Command("reset_onboarding"))
async def cmd_reset_onboarding(message: Message):
    if not await is_admin(message.from_user.id):
        return
    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("Формат: <code>/reset_onboarding USER_ID</code>", parse_mode="HTML")
        return
    try:
        target_id = int(parts[1])
    except ValueError:
        await message.answer("USER_ID должен быть числом.")
        return

    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "UPDATE users SET onboarding_done=FALSE WHERE telegram_id=$1 RETURNING telegram_id",
            target_id,
        )
    if not row:
        await message.answer(f"Пользователь {target_id} не найден.")
        return
    await message.answer(f"🔄 Онбординг сброшен для {target_id}.")
