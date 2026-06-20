# Бэклог задач — ВашСад Бот
# Задачи для реализации в Claude Code по приоритету

---

## ✅ ВЫПОЛНЕНО

### TASK-001: PostgreSQL-хранилище ✅
- `services/database.py` — полная реализация с asyncpg + Neon PostgreSQL
- Таблицы: users, chat_history, orders, diagnoses, user_plants, favorites, garden_tasks
- `handlers/chat.py`, `handlers/plants.py`, `handlers/order.py` — переведены с in-memory на async DB

### TASK-002: FSM-диалог /plan ✅
- `handlers/plan.py` — 5 шагов FSM (площадь → форма → стороны света → что есть → пожелания)
- Claude AI генерирует текстовый план участка

### TASK-005: Профиль пользователя (/profile) ✅
- Добавлен в `handlers/start.py`
- Показывает: имя, статус подписки, дата регистрации, остаток лимитов

### TASK-011: PostgreSQL ✅ (было в плане как Этап 1)
- Уже используется с asyncpg через Neon (serverless PostgreSQL)

### TASK-012: Telegram Mini App ✅ (было в плане как Этап 3)
- `C:/Projects/vashsad-miniapp` — Next.js 15, задеплоен на Vercel
- Экраны: Garden, Plants (избранное), Diagnosis (Claude Vision), Orders, Profile

---

## 🔴 ВЫСОКИЙ ПРИОРИТЕТ (делать сейчас)

### TASK-003: Подключить welcome-картинку в /start
**Файлы:** `handlers/start.py`, `.env`
**Описание:**
- Отправить боту фото маскота → получить `file_id` из ответа
- Добавить в `.env`: `WELCOME_IMAGE_URL=<file_id>`
- Логика уже готова в `cmd_start()` — проверяет `WELCOME_IMAGE_URL`

---

### TASK-004: Деплой на VPS ✅ ЧАСТИЧНО
**Файлы:** `Dockerfile` ✅, `requirements.txt` ✅, `.env` (нужно заполнить на VPS)
**Описание:**
- `Dockerfile` создан (python:3.12-slim + asyncpg deps)
- `requirements.txt` обновлён (добавлен `anthropic>=0.28.0`)
- Осталось:
  - Арендовать VPS (Timeweb/Beget/Selectel)
  - Скопировать `.env` с реальными ключами
  - `docker build -t vashsad-bot . && docker run -d --env-file .env vashsad-bot`
  - Или использовать systemd (инструкция в `docs/05_Deploy.md`)

---

## 🟡 СРЕДНИЙ ПРИОРИТЕТ (Этап 1)

### TASK-006: Реферальная программа
**Файлы:** `handlers/start.py`, `services/database.py`
**Описание:**
- `/start?start=REF_CODE` — отслеживать реферала
- При регистрации через реферала — +3 бонусных сообщения рефереру
- `/referral` — получить свою реферальную ссылку

---

### TASK-007: Портфолио с фото (/portfolio)
**Файлы:** `handlers/start.py` (команда `/portfolio` уже есть — редиректит в Mini App)
**Описание:**
- Создать список проектов в `config.py` (name, description, photo_file_id)
- Отправлять медиагруппу с фото и подписями
- Кнопка «Хочу такой проект» → /order

---

### TASK-008: Сезонные уведомления
**Файлы:** новый `services/scheduler.py`
**Описание:**
- При старте бота запускать APScheduler
- Апрель: «Пора сажать рассаду! Вот план на апрель...»
- Август: «Самое время планировать сад на следующий год»
- Уведомления всем пользователям из БД (кроме заблокировавших бота)

---

## 🟢 НИЗКИЙ ПРИОРИТЕТ (Этап 2+)

### TASK-009: Автооплата YooKassa
- Интеграция платёжной системы для стартовых услуг
- Webhook для подтверждения оплаты

### TASK-010: Redis FSM Storage
- Уже используется Upstash Redis в miniapp
- Для бота: заменить `MemoryStorage` на `RedisStorage` (aiogram-redis)
- FSM-данные переживают рестарт бота

---

## Как работать с этим файлом в Claude Code

```
Открой задачу TASK-004 из docs/00_Backlog.md и реализуй её.
Все детали архитектуры в docs/02_Architecture.md.
После выполнения запиши summary в 03-Daily/YYYY-MM-DD.md.
```
