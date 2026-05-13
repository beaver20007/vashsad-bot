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
vashsad/
├── bot.py                    # Точка входа
├── config.py                 # Настройки (.env)
├── keyboards.py              # Все InlineKeyboard
├── handlers/
│   ├── start.py              # /start, главное меню
│   ├── chat.py               # AI-чат (текстовые сообщения)
│   ├── plants.py             # Подбор растений (FSM)
│   ├── photo.py              # Фото-диагностика (Claude Vision)
│   ├── price.py              # Прайс-лист, подписка
│   └── order.py              # Заказ услуг, бриф проекта (FSM)
└── services/
    ├── ai.py                 # Claude API — чат + Vision
    └── storage.py            # Хранилище пользователей (in-memory → DB)
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
FREE_CHAT_LIMIT=10
FREE_PHOTO_LIMIT=3
FREE_PLANTS_LIMIT=3
```

## Current Sprint
- [ ] Подключить SQLite для хранения пользователей (заменить in-memory storage)
- [ ] Добавить FSM-диалог генерации плана участка
- [ ] Настроить уведомления дизайнеру при новой заявке
- [ ] Добавить welcome-картинку с маскотом в /start

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
