# Архитектура — ВашСад Бот v1.0

---

## 1. Обзор архитектуры

```
┌─────────────────────────────────────────────────────┐
│                   ПОЛЬЗОВАТЕЛЬ                       │
│              Telegram App (любая ОС)                 │
└──────────────────────┬──────────────────────────────┘
                       │ HTTPS / Telegram API
┌──────────────────────▼──────────────────────────────┐
│              TELEGRAM BOT API                        │
│         api.telegram.org (Long Polling)              │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────┐
│                  ВАШСАД БОТ                          │
│              Python 3.12 + aiogram 3.x               │
│                                                      │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────┐   │
│  │ handlers │  │keyboards │  │    FSM States    │   │
│  │ /start   │  │ main_menu│  │ PlantsForm       │   │
│  │ /chat    │  │ price_kb │  │ OrderForm        │   │
│  │ /plants  │  │ order_kb │  │ PlanForm         │   │
│  │ /photo   │  └──────────┘  └──────────────────┘   │
│  │ /price   │                                        │
│  │ /order   │  ┌──────────────────────────────────┐  │
│  └──────────┘  │           SERVICES               │  │
│                │  ai.py — Claude API               │  │
│                │  storage.py — User storage        │  │
│                └──────────────────────────────────┘  │
└──────┬─────────────────────────┬────────────────────┘
       │                         │
       ▼                         ▼
┌─────────────┐         ┌────────────────┐
│ ANTHROPIC   │         │   DATABASE     │
│ Claude API  │         │ SQLite (MVP)   │
│ claude-     │         │ PostgreSQL     │
│ sonnet-4    │         │ (production)   │
└─────────────┘         └────────────────┘
```

---

## 2. Технологический стек

### MVP (запускается прямо сейчас)
| Компонент | Технология | Зачем |
|-----------|-----------|-------|
| Telegram Bot | aiogram 3.x | Основной канал, FSM |
| AI | Claude API (Anthropic) | Чат + Vision для фото |
| База данных | In-memory → SQLite | Хранение пользователей |
| FSM Storage | MemoryStorage | Состояния диалогов |
| Окружение | python-dotenv | Переменные окружения |
| HTTP Client | aiohttp | Запросы к Claude API |

### Production (Этап 2+)
| Компонент | Технология | Зачем |
|-----------|-----------|-------|
| База данных | PostgreSQL 16 | Надёжное хранение |
| Кеш / FSM | Redis 7 | FSM состояния, очереди |
| Платежи | YooKassa | Оплата услуг |
| Деплой | Docker + VPS | Работа 24/7 |
| Уведомления | Celery Beat | Сезонные рассылки |

---

## 3. Структура базы данных (SQLite MVP)

```sql
-- Пользователи
CREATE TABLE users (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id     INTEGER UNIQUE NOT NULL,
    username        TEXT,
    first_name      TEXT,
    region          TEXT,
    is_subscribed   BOOLEAN DEFAULT FALSE,
    chat_count      INTEGER DEFAULT 0,
    photo_count     INTEGER DEFAULT 0,
    plants_count    INTEGER DEFAULT 0,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

-- История чата (для контекста AI)
CREATE TABLE chat_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER REFERENCES users(id),
    role        TEXT NOT NULL,  -- 'user' | 'assistant'
    content     TEXT NOT NULL,
    created_at  TEXT NOT NULL
);

-- Заявки на услуги
CREATE TABLE orders (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER REFERENCES users(id),
    service_key     TEXT NOT NULL,
    service_name    TEXT NOT NULL,
    price           INTEGER NOT NULL,
    contact         TEXT,
    status          TEXT DEFAULT 'new',  -- new|confirmed|done
    brief           TEXT,  -- JSON бриф для проекта
    created_at      TEXT NOT NULL
);

-- Индексы
CREATE INDEX idx_users_tg ON users(telegram_id);
CREATE INDEX idx_chat_user ON chat_history(user_id);
CREATE INDEX idx_orders_user ON orders(user_id);
```

---

## 4. Claude API — интеграция

### Текстовый чат
```python
POST https://api.anthropic.com/v1/messages
{
  "model": "claude-sonnet-4-20250514",
  "max_tokens": 1500,
  "system": "...",  # Системный промпт дизайнера
  "messages": [     # История диалога (до 10 сообщений)
    {"role": "user", "content": "..."},
    {"role": "assistant", "content": "..."}
  ]
}
```

### Vision (фото-диагностика)
```python
POST https://api.anthropic.com/v1/messages
{
  "model": "claude-sonnet-4-20250514",
  "messages": [{
    "role": "user",
    "content": [
      {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": "..."}},
      {"type": "text", "text": "Что не так с этим растением?"}
    ]
  }]
}
```

### Системный промпт (ключевой)
```
Ты — AI-помощник профессионального ландшафтного дизайнера,
специализация: природный стиль садов, Нижегородская и Владимирская области.

Правила:
- Отвечай по-русски, дружелюбно и профессионально
- Давай конкретные советы с учётом климата Средней полосы России
- Рекомендуй растения подходящие для зоны 4-5 (Нижний Новгород)
- При сложных задачах предлагай обратиться к дизайнеру через /order
- Максимум 400 слов в ответе
```

---

## 5. Деплой (Production)

### VPS минимальные требования
- CPU: 1 vCPU
- RAM: 1 GB
- Disk: 10 GB SSD
- OS: Ubuntu 22.04 LTS
- Стоимость: ~300–500 ₽/мес (Timeweb, Beget, Selectel)

### docker-compose.yml (базовый)
```yaml
version: "3.9"
services:
  bot:
    build: .
    restart: always
    env_file: .env
    volumes:
      - ./data:/app/data  # SQLite файл
    depends_on:
      - redis

  redis:
    image: redis:7-alpine
    restart: always
    volumes:
      - redis_data:/data

volumes:
  redis_data:
```

### Dockerfile
```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["python", "bot.py"]
```

---

## 6. Безопасность

- API ключи ТОЛЬКО в .env, никогда в коде
- .env добавлен в .gitignore
- Telegram ID дизайнера защищён — только ему приходят уведомления о заявках
- Фото пользователей не сохраняются на диск (обрабатываются в памяти)
- Лимиты Free-тира защищают от злоупотреблений
