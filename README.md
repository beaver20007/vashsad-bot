# ВашСад — Telegram Bot + Mini App

AI-помощник дипломированного ландшафтного дизайнера. Специализация — природный стиль садов, Нижегородская и Владимирская области.

Проект состоит из двух частей:
- **`vashsad-full/`** — Python Telegram-бот (aiogram 3.x)
- **`vashsad-miniapp/`** — Next.js Mini App, открывается внутри Telegram

---

## Features

### AI-возможности
- AI-чат с ландшафтным дизайнером на базе Claude Sonnet
- Фото-диагностика растений (Claude Vision — определяет болезни и вредителей по фото)
- Подбор растений с учётом климата, условий участка и личных предпочтений
- Генерация плана участка через FSM-диалог

### Команды бота
| Команда | Описание |
|---------|----------|
| `/start` | Приветствие, главное меню, кнопка открытия Mini App |
| `/profile` | Лимиты использования, статус подписки |
| `/plants` | Подбор растений (FSM-диалог) |
| `/order` | Заказ услуг / бриф проекта (FSM-диалог) |
| `/booking` | Запись на консультацию |
| `/price` | Прайс-лист и тарифы |
| `/guide` | Гид по уходу за растениями |
| `/export` | Экспорт персональных данных |
| `/referral` | Реферальная программа |
| `/promo` | Ввод промокода |
| `/admin` | Панель администратора (только для дизайнера) |

### Mini App (экраны)
| Экран | Путь | Описание |
|-------|------|----------|
| Мой сад | `/garden` | Данные участка пользователя, фотогалерея |
| Каталог растений | `/plants` | Каталог с поиском, лайками, избранным |
| Диагностика | `/diagnose` | Загрузка фото и AI-диагностика |
| AI-чат | `/chat` | Чат с дизайнером прямо в приложении |
| Дневник сада | `/diary` | Записи о растениях и работах |
| Карта участка | `/garden-map` | Интерактивная карта зон |
| Питомники | `/nurseries` | Ближайшие питомники на карте |
| История заказов | `/orders` | Статусы заявок и проектов |
| Профиль | `/profile` | Подписка, лимиты, настройки |

### Платежи
- **YooKassa** — банковские карты, СБП (подписка, оплата услуг)
- **Telegram Stars** — нативная оплата внутри Telegram
- Промокоды со скидками
- Реферальная программа

### Уведомления дизайнеру
- Telegram (мгновенно при новой заявке)
- Email через Resend
- SMS через smsc.ru

---

## Tech Stack

| Слой | Технология |
|------|-----------|
| Бот | Python 3.12, aiogram 3.x |
| AI | Anthropic Claude (`claude-sonnet-4-20250514`), Vision API |
| Mini App | Next.js 14 (App Router), TypeScript |
| База данных | PostgreSQL (Neon) — asyncpg |
| FSM / кеш | Redis (Upstash или self-hosted) |
| Планировщик | APScheduler |
| Платежи | YooKassa, Telegram Stars |
| PDF | WeasyPrint / ReportLab |
| Email | Resend |
| SMS | smsc.ru |
| Деплой (бот) | Docker, Railway |
| Деплой (miniapp) | Vercel |

---

## Architecture

```
                          ┌──────────────────────────┐
                          │      Telegram Client      │
                          └────────────┬─────────────┘
                                       │
                    ┌──────────────────┼──────────────────┐
                    │                  │                  │
             ┌──────▼──────┐   ┌───────▼───────┐         │
             │  Python Bot  │   │   Mini App    │         │
             │ (aiogram 3)  │   │  (Next.js 14) │         │
             └──────┬──────┘   └───────┬───────┘         │
                    │                  │                  │
        ┌───────────┼──────────────────┤                  │
        │           │                  │                  │
   ┌────▼────┐ ┌────▼────┐      ┌──────▼──────┐   ┌──────▼──────┐
   │ Claude  │ │  Neon   │      │   Upstash   │   │  YooKassa   │
   │   API   │ │Postgres │      │    Redis    │   │  / Stars    │
   └─────────┘ └─────────┘      └─────────────┘   └─────────────┘
                    │
          ┌─────────┴─────────┐
          │  Notifications    │
          │  Telegram/Email/  │
          │       SMS         │
          └───────────────────┘
```

---

## Quick Start

### Требования
- Python 3.12+
- Docker и Docker Compose
- Аккаунт Neon (PostgreSQL) или любой PostgreSQL-хостинг
- Аккаунт Upstash (Redis) или локальный Redis
- API-ключи: Anthropic, Telegram Bot Token

### 1. Клонирование

```bash
git clone https://github.com/Beaver20007/vashsad-full.git
cd vashsad-full
```

### 2. Переменные окружения

```bash
cp .env.example .env
# Заполни .env (см. раздел "Environment Variables" ниже)
```

### 3. Запуск через Docker Compose

```bash
docker-compose up --build
```

Бот запустится с локальным Redis. PostgreSQL настраивается через `DATABASE_URL` в `.env` (Neon или другой внешний хостинг).

### 4. Запуск без Docker (разработка)

```bash
pip install -r requirements.txt
python bot.py
```

---

## Environment Variables

### Бот (`vashsad-full/.env`)

| Переменная | Обязательная | Описание |
|-----------|:------------:|---------|
| `TELEGRAM_BOT_TOKEN` | Да | Токен бота от @BotFather |
| `ANTHROPIC_API_KEY` | Да | API-ключ Anthropic (`sk-ant-...`) |
| `DATABASE_URL` | Да | PostgreSQL строка подключения (`postgresql://...`) |
| `DESIGNER_TELEGRAM_ID` | Да | Telegram ID дизайнера для уведомлений |
| `DESIGNER_NAME` | Да | Имя дизайнера (именительный падеж) |
| `DESIGNER_NAME_GEN` | Да | Имя дизайнера (родительный падеж, для «помощник Имени») |
| `REDIS_URL` | Да | Redis URL (`redis://...` или Upstash URL) |
| `UPSTASH_REDIS_REST_URL` | Нет | REST URL Upstash (если не используешь `REDIS_URL`) |
| `UPSTASH_REDIS_REST_TOKEN` | Нет | Токен Upstash REST API |
| `MINI_APP_URL` | Нет | URL Mini App на Vercel (для кнопки WebApp) |
| `MINIAPP_URL` | Нет | Дублирует `MINI_APP_URL` (используется в deep-links) |
| `WELCOME_IMAGE_URL` | Нет | `file_id` приветственного изображения в Telegram |
| `FREE_CHAT_LIMIT` | Нет | Лимит AI-сообщений на Free-тире (default: 10) |
| `FREE_PHOTO_LIMIT` | Нет | Лимит фото-диагностик на Free-тире (default: 3) |
| `FREE_PLANTS_LIMIT` | Нет | Лимит подборов растений на Free-тире (default: 3) |
| `SUBSCRIPTION_PRICE` | Нет | Цена подписки в рублях (default: 299) |
| `YOOKASSA_SHOP_ID` | Нет | ID магазина YooKassa |
| `YOOKASSA_SECRET_KEY` | Нет | Секретный ключ YooKassa |
| `YOOKASSA_RETURN_URL` | Нет | URL редиректа после оплаты |
| `YOOKASSA_WEBHOOK_ENABLED` | Нет | Включить webhook-сервер (`1` после деплоя) |
| `OPENWEATHER_API_KEY` | Нет | Ключ OpenWeatherMap (для виджета погоды в miniapp) |
| `BOT_USERNAME` | Нет | Username бота без `@` (для ссылок) |
| `ADMIN_TOKEN` | Нет | Секретный токен для дашборда `/admin` |

### Mini App (`vashsad-miniapp/.env.local`)

| Переменная | Обязательная | Описание |
|-----------|:------------:|---------|
| `DATABASE_URL` | Да | Neon PostgreSQL строка подключения |
| `TELEGRAM_BOT_TOKEN` | Да | Токен бота (для HMAC-валидации `initData`) |
| `ANTHROPIC_API_KEY` | Да | API-ключ Anthropic |
| `OPENWEATHER_API_KEY` | Нет | Ключ OpenWeatherMap |

---

## Project Structure

```
vashsad-full/
├── bot.py                    # Точка входа, инициализация роутеров
├── config.py                 # Все настройки из .env
├── keyboards.py              # InlineKeyboard и ReplyKeyboard
├── setup_bot.py              # Настройка команд BotFather (запустить один раз)
├── Dockerfile
├── docker-compose.yml        # Бот + Redis
├── requirements.txt
├── .env.example
│
├── handlers/
│   ├── start.py              # /start, главное меню, /profile
│   ├── chat.py               # AI-чат (ВСЕГДА регистрируется последним)
│   ├── plants.py             # Подбор растений (FSM)
│   ├── photo.py              # Фото-диагностика (Claude Vision)
│   ├── price.py              # Прайс-лист
│   ├── order.py              # Заказ услуг, бриф (FSM)
│   ├── plan.py               # Генерация плана участка (FSM)
│   ├── booking.py            # Запись на консультацию (FSM)
│   ├── payment.py            # Оплата YooKassa
│   ├── payment_stars.py      # Оплата Telegram Stars
│   ├── referral.py           # Реферальная программа
│   ├── promo.py              # Промокоды
│   ├── onboarding.py         # Онбординг новых пользователей
│   ├── admin.py              # Панель администратора
│   ├── feedback.py           # Отзывы и NPS
│   ├── guide.py              # Гид по уходу за растениями
│   ├── inline_mode.py        # Inline-режим бота
│   ├── moderation.py         # Бан, BanCheckMiddleware
│   ├── export.py             # Экспорт данных пользователя
│   ├── poll.py               # Опросы
│   └── watering.py           # Напоминания о поливе
│
└── services/
    ├── ai.py                 # Claude API — чат + Vision
    ├── database.py           # PostgreSQL (asyncpg), init_db
    ├── storage.py            # Legacy in-memory storage
    ├── notifications.py      # Уведомления дизайнеру
    ├── email_service.py      # Resend
    ├── sms_service.py        # smsc.ru
    ├── payment_service.py    # YooKassa интеграция
    ├── pdf_generator.py      # Генерация PDF-отчётов
    ├── scheduler.py          # APScheduler (сезонные рассылки)
    └── webhook_server.py     # aiohttp-сервер для YooKassa webhook
```

---

## Деплой на VPS

Пошаговая инструкция для деплоя на чистый Ubuntu 22.04 VPS.

### 1. Требования

- Ubuntu 22.04 LTS
- Docker 24+ и Docker Compose v2 (`docker compose`)
- Домен (обязателен, если хочешь получать YooKassa webhook по HTTPS)
- Открытые порты: 80, 443 (для webhook), 22 (SSH)

```bash
# Установка Docker на Ubuntu 22.04
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
newgrp docker
```

### 2. Клонирование репозитория

```bash
git clone https://github.com/Beaver20007/vashsad-full.git
cd vashsad-full
```

### 3. Создание файла окружения

```bash
cp .env.example .env
nano .env
```

Обязательные переменные для production:

| Переменная | Описание |
|-----------|---------|
| `TELEGRAM_BOT_TOKEN` | Токен бота от @BotFather |
| `ANTHROPIC_API_KEY` | API-ключ Anthropic (`sk-ant-...`) |
| `DATABASE_URL` | PostgreSQL строка подключения |
| `REDIS_URL` | Redis URL (`redis://redis:6379/0` для docker-compose) |
| `DESIGNER_TELEGRAM_ID` | Telegram ID дизайнера для уведомлений |
| `DESIGNER_NAME` | Имя дизайнера (именительный падеж) |
| `DESIGNER_NAME_GEN` | Имя дизайнера (родительный падеж) |
| `YOOKASSA_SHOP_ID` | ID магазина YooKassa (если нужны платежи) |
| `YOOKASSA_SECRET_KEY` | Секретный ключ YooKassa |
| `WEBHOOK_URL` | Публичный URL для YooKassa webhook (опционально) |
| `MINI_APP_URL` | URL Mini App на Vercel (для кнопки WebApp) |
| `BOT_USERNAME` | Username бота без `@` |
| `ADMIN_TOKEN` | Секрет для дашборда `/admin` |

### 4. Запуск

```bash
docker compose up -d --build
```

Бот и Redis поднимутся в контейнерах. PostgreSQL берётся из внешнего `DATABASE_URL` (Neon или собственный Postgres).

### 5. Проверка перед запуском

```bash
python scripts/pre_deploy_check.py
```

Скрипт проверит наличие всех обязательных переменных и доступность сервисов.

### 6. Настройка BotFather

После первого запуска выполни один раз:

```bash
python setup_bot.py
```

Скрипт установит имя, описание, фото профиля и список команд бота через Bot API.

### 7. Webhook для YooKassa (опционально)

Для получения уведомлений об оплате через YooKassa:

1. Укажи в `.env`:
   ```
   WEBHOOK_URL=https://yourdomain.com/webhook/yookassa
   YOOKASSA_WEBHOOK_ENABLED=1
   ```
2. Настрой обратный прокси (nginx / Caddy) для HTTPS на порт `8080` (webhook-сервер бота).
3. Перезапусти бот: `docker compose restart bot`

### 8. Мониторинг и логи

```bash
# Следить за логами бота в реальном времени
docker compose logs -f bot

# Статус контейнеров
docker compose ps

# Перезапуск после изменения .env
docker compose restart bot
```

---

## Secrets для GitHub Actions

При настройке CI/CD через `.github/workflows/` добавь в Settings → Secrets → Actions следующие секреты:

| Secret | Описание |
|--------|---------|
| `DOCKER_USERNAME` | Логин Docker Hub (для пуша образа) |
| `DOCKER_PASSWORD` | Пароль / Access Token Docker Hub |
| `VPS_HOST` | IP-адрес или домен VPS сервера |
| `VPS_USER` | SSH-пользователь на VPS (например, `ubuntu`) |
| `VPS_KEY` | Приватный SSH-ключ для доступа к VPS (содержимое `~/.ssh/id_rsa`) |

---

## Deployment

### Docker (VPS / Railway)

```bash
# Собрать и запустить
docker-compose up -d --build

# Посмотреть логи
docker-compose logs -f bot
```

`docker-compose.yml` запускает бота и Redis. База данных (PostgreSQL/Neon) — внешний сервис, настраивается через `DATABASE_URL`.

### Railway

1. Создай новый проект на [railway.app](https://railway.app)
2. Подключи репозиторий `vashsad-full`
3. Добавь все переменные окружения через Variables
4. Railway автоматически использует `Dockerfile`

### Mini App (Vercel)

```bash
cd vashsad-miniapp
vercel deploy
```

Добавь переменные окружения в настройках Vercel-проекта. Укажи URL деплоя в `MINI_APP_URL` бота.

### Настройка BotFather

После деплоя выполни один раз:

```bash
python setup_bot.py
```

Скрипт установит имя, описание, фото и команды бота через Bot API.

---

## Development Notes

### Добавить новый хендлер

1. Создай `handlers/my_feature.py` с `router = Router()`
2. Импортируй и зарегистрируй роутер в `bot.py`:
   ```python
   from handlers.my_feature import router as my_feature_router
   # ...
   dp.include_routers(..., my_feature_router, chat_router)  # chat_router — ВСЕГДА последним
   ```
3. Если хендлер создаёт таблицы в БД — добавь вызов функции инициализации в `main()` в `bot.py`

### Важные правила

- `chat_router` регистрируется **последним** — он перехватывает любое текстовое сообщение
- `BanCheckMiddleware` применяется ко всем роутерам автоматически
- Все тексты сообщений бота — на **русском языке**
- Используй `async/await` везде — бот полностью асинхронный
- FSM-состояния храним в Redis (`RedisStorage`), не в памяти

### База данных

Инициализация схемы происходит автоматически при старте (`services/database.py` → `init_db()`). Для добавления новых таблиц:
- Либо добавь `CREATE TABLE IF NOT EXISTS` в `init_db()`
- Либо создай отдельную функцию `create_<feature>_table()` и вызови её из `main()` в `bot.py`

### AI-модель

```python
# services/ai.py
MODEL = "claude-sonnet-4-20250514"
# Vision (фото-диагностика): передаётся base64-изображение в messages
```

### Mini App API

Все API-роуты находятся в `vashsad-miniapp/app/api/`. Аутентификация — через `Telegram.WebApp.initData` (HMAC-подпись проверяется на сервере).

| Метод | Передача `initData` |
|-------|---------------------|
| GET | Заголовок `x-init-data` |
| POST / PATCH / DELETE | Поле `"initData"` в JSON-теле |

Rate limit: 60 запросов в 60 секунд на IP.

---

## Links

- [Anthropic Console](https://console.anthropic.com) — управление API-ключами
- [Neon](https://neon.tech) — serverless PostgreSQL
- [Upstash](https://upstash.com) — serverless Redis
- [YooKassa](https://yookassa.ru) — приём платежей в России
- [Resend](https://resend.com) — транзакционные email
- [smsc.ru](https://smsc.ru) — SMS-рассылки
