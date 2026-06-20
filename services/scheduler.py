"""
services/scheduler.py
Сезонные рассылки через APScheduler.
"""
import logging
import aiohttp
from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from config import DESIGNER_TELEGRAM_ID
from services.database import get_all_user_ids, get_users_with_tasks_due_today
from services.notifications import send_batch

log = logging.getLogger(__name__)

SEASONAL_MESSAGES = {
    (4, 1): (
        "🌱 <b>Апрель — время сеять рассаду!</b>\n\n"
        "Пора подготовить грядки и высеять томаты, перцы и баклажаны на рассаду.\n\n"
        "💡 Совет: природный сад начинается с правильного выбора растений под ваш климат.\n\n"
        "Нужна помощь с планом посадок? Пишите 🌿"
    ),
    (6, 1): (
        "☀️ <b>Июнь — сезон активного ухода!</b>\n\n"
        "Самое время мульчировать грядки, подкармливать многолетники и следить за влажностью.\n\n"
        "📸 Есть проблемы с растениями? Пришлите фото — определим болезнь за секунды."
    ),
    (8, 15): (
        "🍂 <b>Август — готовим сад к осени!</b>\n\n"
        "Самое время собрать урожай, посеять сидераты и спланировать изменения на следующий год.\n\n"
        "🗺 Хотите обновить сад весной? Сейчас лучшее время для проекта!"
    ),
    (10, 1): (
        "❄️ <b>Октябрь — укрываем многолетники!</b>\n\n"
        "Розы, гортензии и теплолюбивые растения нуждаются в укрытии до первых морозов.\n\n"
        "📋 Нужен сезонный план ухода? Составлю персональный — <b>3 500 ₽</b> 🌿"
    ),
}


async def broadcast_personalized_seasonal(bot: Bot, base_text: str) -> None:
    """Personalized seasonal broadcast using user's plant list."""
    from services.database import get_pool
    pool = await get_pool()
    async with pool.acquire() as conn:
        users = await conn.fetch(
            """SELECT u.telegram_id, u.first_name, u.region,
                      COALESCE(
                        (SELECT string_agg(plant_name, ', ') FROM user_plants WHERE telegram_id = u.telegram_id LIMIT 5),
                        NULL
                      ) as plants
               FROM users WHERE is_banned = FALSE OR is_banned IS NULL"""
        )

    sent, failed = 0, 0
    for user in users:
        try:
            plants_mention = f"\n\n🌿 В вашем саду: {user['plants']}" if user['plants'] else ""
            text = base_text + plants_mention
            await bot.send_message(user['telegram_id'], text, parse_mode="HTML")
            sent += 1
        except (TelegramForbiddenError, TelegramBadRequest):
            failed += 1
        except Exception as e:
            log.warning("Ошибка персонализированной рассылки для %s: %s", user['telegram_id'], e)
            failed += 1
    log.info("Персонализированная сезонная рассылка: отправлено %d, ошибок %d", sent, failed)


async def send_test_broadcast(bot: Bot, text: str) -> None:
    """Manual test broadcast — call from admin handler."""
    await broadcast_personalized_seasonal(bot, text)


async def broadcast_seasonal(bot: Bot, text: str) -> None:
    """Рассылка всем пользователям с rate-limiting (25 msg/s). Игнорирует заблокировавших бота."""
    user_ids = await get_all_user_ids()
    sent, failed = await send_batch(bot, user_ids, text)
    log.info("Сезонная рассылка: отправлено %d, ошибок %d", sent, failed)


async def notify_garden_tasks(bot: Bot) -> None:
    """Ежедневная рассылка пользователям с задачами на сегодня."""
    users = await get_users_with_tasks_due_today()
    sent, failed = 0, 0
    for user in users:
        try:
            await bot.send_message(
                user["telegram_id"],
                "🌿 Сегодня есть задачи по уходу за садом! Откройте ВашСад для деталей.",
            )
            sent += 1
        except (TelegramForbiddenError, TelegramBadRequest):
            failed += 1
        except Exception as e:
            log.warning("Ошибка уведомления для %s: %s", user["telegram_id"], e)
            failed += 1
    log.info("Уведомления о задачах: отправлено %d, ошибок %d", sent, failed)


async def schedule_booking_reminders(bot: Bot, telegram_id: int, booking_id: int, slot_dt: "datetime") -> None:
    """Планирует напоминания за 24ч и 1ч до консультации."""
    from datetime import datetime, timedelta
    remind_24h = slot_dt - timedelta(hours=24)
    remind_1h  = slot_dt - timedelta(hours=1)
    now = datetime.now()

    if remind_24h > now:
        _scheduler_instance.add_job(
            _send_booking_reminder, "date",
            run_date=remind_24h,
            args=[bot, telegram_id, slot_dt, "24h"],
            id=f"booking_remind_24h_{booking_id}",
            replace_existing=True,
        )
    if remind_1h > now:
        _scheduler_instance.add_job(
            _send_booking_reminder, "date",
            run_date=remind_1h,
            args=[bot, telegram_id, slot_dt, "1h"],
            id=f"booking_remind_1h_{booking_id}",
            replace_existing=True,
        )
    log.info("Напоминания о записи #%s запланированы", booking_id)


async def _send_booking_reminder(bot: Bot, telegram_id: int, slot_dt: "datetime", kind: str) -> None:
    from aiogram.exceptions import TelegramForbiddenError
    label = "24 часа" if kind == "24h" else "1 час"
    text = (
        f"⏰ <b>Напоминание о консультации</b>\n\n"
        f"До встречи с дизайнером осталось <b>{label}</b>!\n"
        f"📅 {slot_dt.strftime('%d %b в %H:%M')}\n\n"
        f"Подготовьте фото участка и список вопросов 🌿"
    )
    try:
        await bot.send_message(telegram_id, text, parse_mode="HTML")
    except TelegramForbiddenError:
        pass
    except Exception as e:
        log.warning("Reminder error for %s: %s", telegram_id, e)


async def schedule_nps(bot: Bot, telegram_id: int, order_id: int) -> None:
    """Планирует NPS-опрос через 3 дня после выполнения заявки."""
    from datetime import datetime, timedelta
    from apscheduler.schedulers.asyncio import AsyncIOScheduler

    # Используем глобальный шедулер из setup_scheduler
    run_at = datetime.now() + timedelta(days=3)
    _scheduler_instance.add_job(
        _send_nps_job,
        "date",
        run_date=run_at,
        args=[bot, telegram_id, order_id],
        id=f"nps_{order_id}",
        replace_existing=True,
    )
    log.info("NPS запланирован для order=%s в %s", order_id, run_at.strftime("%d.%m %H:%M"))


async def _send_nps_job(bot: Bot, telegram_id: int, order_id: int) -> None:
    from handlers.feedback import send_nps_survey
    await send_nps_survey(bot, telegram_id, order_id)


async def schedule_watering_reminder(bot, telegram_id: int, plants: str, time_str: str, frequency: str):
    if not _scheduler_instance:
        return
    from apscheduler.triggers.cron import CronTrigger
    from datetime import datetime

    t = datetime.strptime(time_str, "%H:%M")
    job_id = f"watering_{telegram_id}_{time_str}"

    freq_map = {
        'daily':  CronTrigger(hour=t.hour, minute=t.minute, timezone="Europe/Moscow"),
        'every2': CronTrigger(day="*/2", hour=t.hour, minute=t.minute, timezone="Europe/Moscow"),
        'twice':  CronTrigger(day_of_week="mon,thu", hour=t.hour, minute=t.minute, timezone="Europe/Moscow"),
        'weekly': CronTrigger(day_of_week="mon", hour=t.hour, minute=t.minute, timezone="Europe/Moscow"),
    }
    trigger = freq_map.get(frequency, freq_map['daily'])

    async def send_reminder():
        try:
            await bot.send_message(
                telegram_id,
                f"💧 <b>Время полить {plants}!</b>\n\nНе забудьте полить ваши растения сегодня 🌱",
                parse_mode="HTML"
            )
        except Exception:
            pass

    _scheduler_instance.add_job(send_reminder, trigger, id=job_id, replace_existing=True)


MONTHLY_TIPS = {
    1: "❄️ Январь — время планировать! Составьте список желаемых растений...",
    2: "🌱 Февраль — сеем томаты и перцы на рассаду...",
    3: "🌷 Март — первые подснежники! Начинаем обрезку роз...",
    4: "🌸 Апрель — высадка рассады в грунт...",
    5: "🌿 Май — активный сезон! Мульчируем грядки...",
    6: "☀️ Июнь — поливаем и следим за вредителями...",
    7: "🍅 Июль — пик урожая! Не забывайте про подкормку...",
    8: "🍂 Август — готовим сад к осени, собираем семена...",
    9: "🍁 Сентябрь — посадка луковичных для весны...",
    10: "🌰 Октябрь — укрываем многолетники на зиму...",
    11: "⛄ Ноябрь — финальная уборка сада...",
    12: "🎄 Декабрь — составляем план на следующий год...",
}

MONTHLY_SEASONAL = {
    1: (
        "🍃 <b>Сезонный календарь садовода — Январь</b>\n\n"
        "Январь — самый спокойный месяц в саду. Проверяйте укрытия многолетников после сильных морозов. "
        "Самое время заказывать семена и изучать каталоги питомников. "
        "Просматривайте луковицы и клубни на хранении, удаляйте подгнившие. "
        "Подкормите зимующих птиц — они помогут справиться с вредителями весной 🐦"
    ),
    2: (
        "🍃 <b>Сезонный календарь садовода — Февраль</b>\n\n"
        "Февраль — начало рассадного сезона для томатов, перцев и баклажанов. "
        "Посейте семена в конце месяца при наличии досветки. "
        "Проверьте и подточите садовый инструмент до начала сезона. "
        "При оттепелях контролируйте состояние укрытых роз — проветривайте, чтобы не выпревали 🌹"
    ),
    3: (
        "🍃 <b>Сезонный календарь садовода — Март</b>\n\n"
        "Март — время санитарной обрезки деревьев и кустарников до пробуждения почек. "
        "Снимайте зимние укрытия постепенно, в пасмурную погоду. "
        "Первые подснежники и крокусы говорят — весна пришла! "
        "Подкормите газон азотным удобрением по талому снегу 🌷"
    ),
    4: (
        "🍃 <b>Сезонный календарь садовода — Апрель</b>\n\n"
        "Апрель — горячая пора! Высаживаем рассаду холодостойких культур: капусту, салат, редис. "
        "Сажаем картофель в прогретую землю. Мульчируем приствольные круги деревьев. "
        "Обрабатываем сад от болезней и вредителей до распускания листьев. "
        "Луковичные уже цветут — не забудьте полить при сухой погоде 🌸"
    ),
    5: (
        "🍃 <b>Сезонный календарь садовода — Май</b>\n\n"
        "Май — главный месяц посадок! После 15 мая высаживаем теплолюбивую рассаду. "
        "Мульчируем все грядки слоем 5–7 см — это сэкономит воду и силы на прополку. "
        "Начинается цветение плодовых деревьев — отличное время для весенней фотосессии сада. "
        "Следите за тлёй на молодых побегах 🌿"
    ),
    6: (
        "🍃 <b>Сезонный календарь садовода — Июнь</b>\n\n"
        "Июнь — время активного роста: подкормите многолетники и розы комплексным удобрением с преобладанием калия. "
        "Следите за влажностью почвы в жаркие дни — полив лучше проводить ранним утром или вечером. "
        "Отцветающие тюльпаны и нарциссы не срезайте до пожелтения листьев. "
        "Самое время посеять однолетники для осеннего цветения: бархатцы, циннии, космею 🌸"
    ),
    7: (
        "🍃 <b>Сезонный календарь садовода — Июль</b>\n\n"
        "Июль — пик сезона! Регулярно собирайте урожай, чтобы стимулировать плодоношение. "
        "Подкармливайте томаты и огурцы каждые 10–14 дней. "
        "Боритесь с фитофторой — профилактические обработки в жаркое влажное лето обязательны. "
        "Не забывайте поливать контейнерные растения — в жару им нужен полив каждый день 🍅"
    ),
    8: (
        "🍃 <b>Сезонный календарь садовода — Август</b>\n\n"
        "Август — время сбора урожая и подготовки к осени. Собирайте семена понравившихся растений. "
        "Сейте сидераты на освободившихся грядках. Начинайте посадку земляники. "
        "Уже можно сажать двулетники: анютины глазки, незабудки, гвоздику турецкую. "
        "Планируйте изменения в саду на следующий год — фотографируйте проблемные места 📸"
    ),
    9: (
        "🍃 <b>Сезонный календарь садовода — Сентябрь</b>\n\n"
        "Сентябрь — лучшее время для посадки луковичных: тюльпанов, нарциссов, крокусов. "
        "Пересаживайте многолетники и делите разросшиеся кусты. "
        "Собирайте поздние сорта яблок и груш. Заготавливайте компост. "
        "Защитите нежные многолетники от ранних заморозков агроволокном 🍁"
    ),
    10: (
        "🍃 <b>Сезонный календарь садовода — Октябрь</b>\n\n"
        "Октябрь — время укрывать теплолюбивые растения. Розы, гортензии метельчатые, клематисы. "
        "Уберите из сада летники, перекопайте грядки. Внесите органику под перекопку. "
        "Посадите озимый чеснок до середины месяца. "
        "Последние луковичные — рябчики, лилии — можно посадить до промерзания почвы 🌰"
    ),
    11: (
        "🍃 <b>Сезонный календарь садовода — Ноябрь</b>\n\n"
        "Ноябрь — финальная уборка сада перед зимой. Укрываем розы лапником или агроволокном. "
        "Белим стволы деревьев для защиты от морозобоин. Убираем падалицу и больные листья. "
        "Раскладываем отравленные приманки от мышей. "
        "Проверяем луковицы и клубни в хранилище — наступает время покоя ⛄"
    ),
    12: (
        "🍃 <b>Сезонный календарь садовода — Декабрь</b>\n\n"
        "Декабрь — время мечтать и планировать! Изучайте каталоги питомников. "
        "Составляйте план посадок на следующий год. Заказывайте семена заранее — лучшие разбирают быстро. "
        "Проверяйте укрытия после снегопадов. Стряхивайте тяжёлый снег с хвойных. "
        "Поставьте ветку из сада в воду — к Новому году распустятся цветы 🎄"
    ),
}


def get_newsletter_content() -> dict:
    """Возвращает контент рассылки на основе текущего месяца."""
    from datetime import datetime
    month = datetime.now().month
    return {
        "tips": (
            f"🌿 <b>Совет месяца от вашего дизайнера</b>\n\n"
            f"{MONTHLY_TIPS[month]}"
        ),
        "seasonal": MONTHLY_SEASONAL[month],
    }


async def send_newsletter_blast(bot: Bot) -> None:
    """Еженедельная рассылка подписчикам по темам из newsletter_subscriptions."""
    from services.database import get_pool
    try:
        pool = await get_pool()
    except Exception as e:
        log.error("send_newsletter_blast: не удалось получить пул БД: %s", e)
        return

    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT telegram_id, topics FROM newsletter_subscriptions WHERE active = TRUE"
            )
    except Exception as e:
        log.error("send_newsletter_blast: ошибка запроса к БД: %s", e)
        return

    import json as _json

    newsletter_content = get_newsletter_content()

    # Группируем получателей по теме для батчевой отправки
    topic_to_ids: dict[str, list[int]] = {}
    for row in rows:
        telegram_id = row["telegram_id"]
        topics = row["topics"]
        if isinstance(topics, str):
            try:
                topics = _json.loads(topics)
            except Exception:
                topics = []
        if not topics:
            continue
        for topic in topics:
            if newsletter_content.get(topic):
                topic_to_ids.setdefault(topic, []).append(telegram_id)

    total_sent, total_failed = 0, 0
    for topic, ids in topic_to_ids.items():
        text = newsletter_content[topic]
        s, f = await send_batch(bot, ids, text)
        total_sent += s
        total_failed += f

    log.info("Рассылка newsletter_blast завершена: отправлено %d, ошибок %d", total_sent, total_failed)


async def self_ping_check(bot: Bot) -> None:
    """Каждые 10 минут проверяет health-check miniapp и уведомляет дизайнера при сбое."""
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                'http://localhost:3000/api/health',
                timeout=aiohttp.ClientTimeout(total=10)
            ) as r:
                if r.status != 200:
                    await bot.send_message(
                        DESIGNER_TELEGRAM_ID,
                        f"⚠️ Health check failed! HTTP {r.status}"
                    )
    except Exception:
        try:
            await bot.send_message(DESIGNER_TELEGRAM_ID, "⚠️ Miniapp не отвечает!")
        except Exception:
            pass


_scheduler_instance: AsyncIOScheduler | None = None


def setup_scheduler(bot: Bot) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="Europe/Moscow")
    for (month, day), text in SEASONAL_MESSAGES.items():
        scheduler.add_job(
            broadcast_personalized_seasonal,
            CronTrigger(month=month, day=day, hour=10, timezone="Europe/Moscow"),
            args=[bot, text],
            id=f"seasonal_{month}_{day}",
            replace_existing=True,
        )
    scheduler.add_job(
        notify_garden_tasks,
        CronTrigger(hour=9, minute=0, timezone="Europe/Moscow"),
        args=[bot],
        name="daily_garden_tasks",
        replace_existing=True,
    )
    # Monthly plant poll — 1st of each month at 10:00
    from handlers.poll import send_monthly_poll as _send_poll
    scheduler.add_job(
        _send_poll,
        CronTrigger(day=1, hour=10, timezone="Europe/Moscow"),
        args=[bot],
        id="monthly_poll",
        replace_existing=True,
    )
    scheduler.add_job(
        send_newsletter_blast,
        CronTrigger(day_of_week="mon", hour=9, timezone="Europe/Moscow"),
        args=[bot],
        id="newsletter_blast",
        replace_existing=True,
    )
    scheduler.add_job(
        self_ping_check,
        'interval',
        minutes=10,
        args=[bot],
        id='self_ping',
        replace_existing=True,
    )
    global _scheduler_instance
    _scheduler_instance = scheduler
    log.info("📅 Планировщик настроен (%d сезонных задач + ежедневные уведомления + newsletter_blast)", len(SEASONAL_MESSAGES))
    return scheduler
