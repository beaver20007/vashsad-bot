# MAX Integration — Claude Code Context

## Проект
Репликация существующих Telegram-ботов на платформу MAX (max.ru, VK).
Стратегия: **адаптер-паттерн** — бизнес-логика не трогается, меняется только транспортный слой.

## Существующие боты (источники)
| Бот | Стек | Статус переноса |
|-----|------|-----------------|
| ВашСад | aiogram 3, Neon PostgreSQL, Upstash Redis FSM, Vercel Mini App | Спринт 1 — пилот |
| docraft.pro | aiogram 3, FastAPI, Supabase, Claude API | Спринт 2 — уведомления |
| VoxSpec | aiogram 3, FastAPI/WebSocket, faster-whisper | Спринт 3 |
| TG Lead Radar / Radar Core | aiogram 3, Telethon, Qdrant | Спринт 3+ |

## Архитектура MAX-интеграции

### Транспортный адаптер
```
src/
  core/
    platform.py       # ABC BotPlatform
    models.py         # Unified Message, User, Callback
  platforms/
    telegram.py       # TelegramPlatform(BotPlatform)
    max_platform.py   # MaxPlatform(BotPlatform)
  handlers/           # Бизнес-логика (без изменений)
```

### MAX API
- Base URL: `https://platform-api.max.ru`
- Auth: заголовок `Authorization: <token>` (НЕ query-параметр)
- Webhook endpoint: только HTTPS, самоподписные сертификаты не принимаются
- Лимит: 30 rps
- Webhook payload: `{"update_type": "...", "user_locale": "...", "message": {...}}`
  > ⚠️ В документации написано что приходит чистый Message — это НЕПРАВДА
  > Реально: мета-контейнер с update_type + user_locale + вложенный объект

### Регистрация бота
- Через @MasterBot в MAX
- Username: >11 символов, заканчивается на `_bot` или `bot`

### Библиотека Python
- Официальная: `max-messenger/max-botapi-python` (PyPI: `max-botapi`)
- Синтаксис близок к aiogram 3
- Webhook через FastAPI + uvicorn

## Известные ограничения MAX vs Telegram
| Функция | Telegram | MAX |
|---------|----------|-----|
| Ban пользователя | Постоянный | Может зайти снова по инвайту |
| Временные ограничения | Есть | Нет — эмулировать |
| Разбан | Предсказуемый | Глючит, часть юзеров не разбанить |
| Mini App / WebApp | Полная поддержка | НЕ поддерживается |
| Long Polling | Production OK | Только разработка |
| Инициировать диалог | Bot.send_message(user_id) | Нельзя без предварительного контакта |

## ENV переменные (добавить к существующим)
```
MAX_BOT_TOKEN_VASHSAD=<token>
MAX_BOT_TOKEN_DOCRAFT=<token>
MAX_WEBHOOK_SECRET=<random_32_bytes>
```

## Webhook роуты (добавить в существующий FastAPI)
```
POST /webhook/telegram   # существующий
POST /webhook/max        # новый
```

## Критические правила
1. **Логировать ВСЁ** что приходит от MAX — без логов дебаг невозможен
2. MAX — вторичный канал, не основной источник дохода
3. Перед каждым методом API — проверять реальный ответ, не доверять доке
4. Хранить версию библиотеки max-botapi в requirements.txt с pin (==x.y.z)
5. Иметь план Б на случай удаления бота: дублировать пользовательскую базу в своей БД

## Спринт 1 — ВашСад MAX бот (текущий)
Цель: базовый бот с командами и inline-кнопками, FSM на Upstash Redis.

### НЕ переносить в спринте 1:
- Mini App (нет аналога в MAX)
- Каталог растений с фото (решить отдельно)
- Автодиагностика через фото (проверить поддержку фото в MAX)

### Переносить:
- /start, /help, /catalog (текстовый)
- Запись на консультацию (FSM)
- Уведомления администратору
