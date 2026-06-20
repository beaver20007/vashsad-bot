# Руководство разработчика ВашСад

## Быстрый старт (локальная разработка)

### 1. Клонирование
git clone ...
cd vashsad-full

### 2. Виртуальное окружение
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
.venv\Scripts\activate  # Windows
pip install -r requirements.txt

### 3. Переменные окружения
cp .env.example .env
# Минимальный набор для разработки:
# TELEGRAM_BOT_TOKEN - от @BotFather (тестовый бот)
# ANTHROPIC_API_KEY - от console.anthropic.com
# DATABASE_URL - Neon бесплатный тариф
# DESIGNER_TELEGRAM_ID - ваш Telegram ID

### 4. Инициализация БД
python scripts/migrate.py
python scripts/seed_plants.py  # необязательно
python scripts/seed_promo.py   # необязательно

### 5. Запуск бота
python bot.py

## Архитектура

### Обработка сообщений
Message -> BanCheckMiddleware -> RateLimitMiddleware -> Router matching -> Handler -> DB/AI/Notify

### FSM состояния
Используется RedisStorage (или MemoryStorage в dev без Redis).
Все FSM в handlers/: plan, order, booking, plants, watering.

### База данных
asyncpg + Neon PostgreSQL. Все операции через services/database.py.
Не делать прямые SQL запросы в handlers — только через database.py функции.

### AI интеграция
services/ai.py -> ask_claude(messages, system_prompt)
Всегда передавать system_prompt с контекстом дизайнера.
Лимиты: FREE_CHAT_LIMIT = 10 сообщений, затем предложение подписки.

## Добавление нового handler
1. Создать handlers/my_feature.py с router = Router()
2. Добавить FSM state group если нужен диалог
3. В bot.py: from handlers.my_feature import router as my_router
4. Добавить в dp.include_routers(..., my_router, ...) — ПЕРЕД chat_router!

## Тесты
pytest tests/ -v
# Или конкретный файл:
pytest tests/test_handlers.py -v
