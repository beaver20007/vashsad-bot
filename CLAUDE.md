# CLAUDE.md — ВашСад Бот
# Этот файл читается Claude Code автоматически на старте каждой сессии

## Project Overview
**Проект:** ВашСад Бот — Telegram-бот дипломированного ландшафтного дизайнера
**Специализация:** Природный стиль садов, Нижегородская и Владимирская области
**Стек:** Python 3.12 · aiogram 3.x · Claude API (Anthropic) · SQLite → PostgreSQL · YooKassa
**Репо:** ~/projects/vashsad
**Документация:** ~/projects/vashsad/docs/

## Architecture
```
vashsad-full/
├── bot.py                        # Точка входа, регистрация роутеров
├── config.py                     # Настройки (.env)
├── keyboards.py                  # Все InlineKeyboard
├── setup_bot.py                  # Настройка команд BotFather
├── Dockerfile / docker-compose.yml
├── handlers/
│   ├── start.py                  # /start, главное меню, /profile
│   ├── chat.py                   # AI-чат (текстовые сообщения)
│   ├── plants.py                 # Подбор растений (FSM)
│   ├── photo.py                  # Фото-диагностика (Claude Vision)
│   ├── price.py                  # Прайс-лист, подписка
│   ├── order.py                  # Заказ услуг, бриф проекта (FSM)
│   ├── admin.py                  # Команды администратора
│   ├── booking.py                # Запись на консультацию (FSM)
│   ├── export.py                 # Экспорт данных пользователя
│   ├── feedback.py               # Отзывы и оценки
│   ├── guide.py                  # Гид по уходу за растениями
│   ├── inline_mode.py            # Inline-режим бота
│   ├── moderation.py             # Модерация контента
│   ├── onboarding.py             # Онбординг новых пользователей
│   ├── payment.py                # Оплата (YooKassa)
│   ├── payment_stars.py          # Оплата Telegram Stars
│   ├── plan.py                   # FSM-диалог генерации плана участка
│   ├── poll.py                   # Опросы пользователей
│   ├── promo.py                  # Промокоды
│   ├── referral.py               # Реферальная программа
│   └── watering.py               # Напоминания о поливе
└── services/
    ├── ai.py                     # Claude API — чат + Vision
    ├── storage.py                # Хранилище пользователей (legacy)
    ├── database.py               # PostgreSQL (asyncpg)
    ├── notifications.py          # Уведомления дизайнеру (Telegram + Email + SMS)
    ├── email_service.py          # Email через Resend
    ├── sms_service.py            # SMS через smsc.ru
    ├── payment_service.py        # YooKassa интеграция
    ├── pdf_generator.py          # Генерация PDF-отчётов
    ├── scheduler.py              # Планировщик задач (apscheduler)
    └── webhook_server.py         # Webhook для YooKassa
```

## Standing Rules
- ВСЕГДА проверяй docs/ перед изменением архитектуры
- Логируй баги, решения и паттерны в 03-Daily/YYYY-MM-DD.md
- Перед созданием нового файла — проверь есть ли уже похожий
- Используй async/await везде — бот полностью асинхронный
- Все тексты сообщений бота — на русском языке
- Не трогай логику лимитов Free-тира без явного указания
- После изменения handlers/ — проверь что роутеры подключены в bot.py

## Key Variables (.env)
```
TELEGRAM_BOT_TOKEN=         # @BotFather
ANTHROPIC_API_KEY=          # console.anthropic.com
DESIGNER_TELEGRAM_ID=       # Telegram ID дизайнера для уведомлений
DESIGNER_NAME=              # Имя дизайнера
DESIGNER_NAME_GEN=          # Имя дизайнера в родительном падеже (для welcome-текста)
FREE_CHAT_LIMIT=10
FREE_PHOTO_LIMIT=3
FREE_PLANTS_LIMIT=3
DATABASE_URL=               # PostgreSQL (asyncpg), напр. Neon
WELCOME_IMAGE_URL=          # URL welcome-картинки для /start
RESEND_API_KEY=             # Email через Resend
DESIGNER_EMAIL=             # Email дизайнера для уведомлений
SMSC_LOGIN=                 # smsc.ru логин
SMSC_PASSWORD=              # smsc.ru пароль
DESIGNER_PHONE=             # Телефон дизайнера для SMS
YOOKASSA_SHOP_ID=           # YooKassa магазин
YOOKASSA_SECRET_KEY=        # YooKassa секрет
WEBHOOK_SECRET=             # Секрет для YooKassa webhook
SENTRY_DSN=                 # Sentry для мониторинга ошибок
UPSTASH_REDIS_REST_URL=     # Redis (Upstash) для кеширования
UPSTASH_REDIS_REST_TOKEN=   # Redis токен
```

## Features
Реализованные функции бота:
- AI-чат с дизайнером (Claude Sonnet, лимиты по тарифу)
- Фото-диагностика растений (Claude Vision)
- Подбор растений (FSM, учёт климата и условий)
- FSM-диалог генерации плана участка
- Заказ услуг / бриф проекта (FSM)
- Запись на консультацию (FSM)
- Прайс-лист и управление подпиской
- Оплата через YooKassa и Telegram Stars
- Реферальная программа и промокоды
- /profile — лимиты и статус подписки
- Welcome-картинка в /start
- Онбординг новых пользователей
- Inline-режим
- Гид по уходу за растениями
- Экспорт данных
- Отзывы и оценки
- Панель администратора
- Уведомления дизайнеру: Telegram + Email (Resend) + SMS (smsc.ru)
- Генерация PDF-отчётов
- Webhook для YooKassa
- Miniapp: Garden / Diagnosis / Favorites, История заявок
- Напоминания о поливе (handlers/watering.py)
- Опросы пользователей (handlers/poll.py)
- Мониторинг ошибок (Sentry)
- Кеширование (Redis / Upstash)
- CI/CD: GitHub Actions → Docker Hub → VPS
- pre-deploy check (scripts/pre_deploy_check.py)

## Current Sprint
- [x] PostgreSQL (Neon) вместо in-memory storage
- [x] FSM-диалог генерации плана участка (handlers/plan.py)
- [x] Уведомления дизайнеру: Telegram + Email (Resend) + SMS (smsc.ru)
- [x] Welcome-картинка в /start (env: WELCOME_IMAGE_URL)
- [x] /profile — лимиты и статус подписки
- [x] Miniapp: Garden / Diagnosis / Favorites подключены к реальному API
- [x] Miniapp: История заявок в разделе «Мой сад»
- [x] Оплата Telegram Stars (handlers/payment_stars.py)
- [x] Реферальная программа (handlers/referral.py)
- [x] Промокоды (handlers/promo.py)
- [x] Онбординг (handlers/onboarding.py)
- [x] Docker / docker-compose.yml
- [x] Настроить BotFather (имя, описание, фото, команды) — setup_bot.py готов
- [x] Напоминания о поливе (handlers/watering.py)
- [x] Опросы пользователей (handlers/poll.py)
- [x] Мониторинг ошибок (Sentry, env: SENTRY_DSN)
- [x] Кеширование (Redis/Upstash, env: UPSTASH_REDIS_REST_URL)
- [x] CI/CD: GitHub Actions → Docker Hub → VPS (auto-deploy on push to main)
- [x] pre-deploy check (scripts/pre_deploy_check.py)
- [x] DESIGNER_NAME_GEN для welcome-текста в родительном падеже
- [x] Задеплоить на VPS

## Miniapp API Routes
Все роуты в `vashsad-miniapp/app/api/`:
| Путь | Назначение |
|------|-----------|
| `/api/admin` | Панель администратора |
| `/api/analytics` | Аналитика |
| `/api/care-plan` | Планы ухода за растениями |
| `/api/chat` | AI-чат |
| `/api/diagnose` | Диагностика по фото |
| `/api/diary` | Дневник сада |
| `/api/export/favorites` | Экспорт избранного |
| `/api/favorites` | Избранные растения |
| `/api/garden` | Данные сада пользователя |
| `/api/garden/photo` | Фото сада |
| `/api/garden-map` | Карта участка |
| `/api/health` | Health-check |
| `/api/likes` | Лайки растений |
| `/api/messages` | История сообщений |
| `/api/notifications` | Push-уведомления |
| `/api/nurseries` | Питомники |
| `/api/order` | Создание заказа |
| `/api/orders` | Список заказов |
| `/api/orders/[id]/status` | Статус заказа |
| `/api/plants` | Каталог растений |
| `/api/plants-photo` | Фото растений |
| `/api/push/send` | Отправка push |
| `/api/push/subscribe` | Подписка на push |
| `/api/reviews` | Отзывы |
| `/api/seed` | Сидирование БД |
| `/api/share` | Поделиться |
| `/api/stars` | Telegram Stars |
| `/api/user` | Профиль пользователя |
| `/api/weather` | Погода |

## Deployment
- Запуск: `docker compose up -d`
- Перед деплоем: `python scripts/pre_deploy_check.py`
- GitHub Actions автоматически деплоит при пуше в `main`
- Требуемые secrets в репо: `DOCKER_USERNAME`, `DOCKER_PASSWORD`, `VPS_HOST`, `VPS_USER`, `VPS_KEY`

## AI Model
Используем: `claude-sonnet-4-20250514`
Эндпоинт: `https://api.anthropic.com/v1/messages`
Vision поддерживается: да (для фото-диагностики растений)

## Session Log
В конце каждой сессии пиши summary в 03-Daily/YYYY-MM-DD.md по шаблону:
```
## Что сделали
## Баги и решения
## Что осталось
```
