# Стратегия совместной разработки ВашСад

## Два проекта — одна система

| Репозиторий | Роль | Хостинг |
|-------------|------|---------|
| vashsad-miniapp (Next.js 16) | Веб-UI: каталог, дизайнер, полив, отзывы | Vercel |
| vashsad-full (Python aiogram 3) | Telegram Bot API: команды, FSM, AI-чат, фото | Railway |

Общая база данных: Neon PostgreSQL — одна, разделяемая обоими.

## Принцип разделения

Бот — единственная точка входа Bot API (long polling).
Miniapp — веб-UI, открывается кнопкой из /start.
Нет дублирования логики: бот не делает UI, miniapp не слушает Telegram.

## Владелец схемы таблиц

| Таблица | Кто создаёт | Кто пишет | Кто читает |
|---------|-------------|-----------|-----------|
| users | Бот (_create_tables) | Оба | Оба |
| plants | Miniapp (миграции) | Miniapp | Бот (read-only) |
| orders | Бот | Оба | /admin miniapp |
| chat_history | Бот | Бот | Miniapp профиль |
| bookmarks, reviews | Miniapp | Miniapp | — |

## Правило изменения схемы

1. Изменить в services/database.py (бот)
2. Использовать в Next.js API routes
3. Деплоить бот → затем miniapp

## Согласованные поля (итог обмена записками 2026-06-21)

```
users: telegram_id, username, first_name, region, is_subscribed,
  chat_count, photo_count, plants_count,
  garden_area (был plot_size), garden_style, onboarding_done,
  push_subscription JSONB, garden_photo_url, season_plan,
  subscription_expires_at, referral_code, referred_by,
  bonus_messages, lang, created_at, updated_at

orders: id, telegram_id, service_type, service_name, service_price,
  area, region, name, phone, email, style, wishes,
  budget_range, status, created_at

plants (read-only для бота): id, slug, name_ru, name_latin, latin_name,
  category, description, photo_url, photo_status, height_m, light,
  drought_tolerant, usda_min, usda_max, tags TEXT[], status,
  peak_spring, peak_summer1, peak_summer2, peak_autumn,
  bloom_color, soil_type, moisture, is_featured
```

## Деплой

- Miniapp → Vercel: `git push main` → auto
- Бот → Railway: `railway up` (railway.toml + Dockerfile готовы)

Env vars бота (все берутся из Vercel env):
```
TELEGRAM_BOT_TOKEN, ANTHROPIC_API_KEY, DATABASE_URL,
REDIS_URL, DESIGNER_TELEGRAM_ID, DESIGNER_NAME, DESIGNER_NAME_GEN,
MINI_APP_URL=https://vashsad-miniapp-pi.vercel.app
```

## Следующие приоритеты

- Бот: деплой Railway → /plan FSM → welcome-фото (/start)
- Miniapp: VAPID push-уведомления → рефакторинг page.tsx
- Общее: монорепо (перенести vashsad-full/ в vashsad-miniapp/bot/) — когда удобно
