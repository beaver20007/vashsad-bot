# Стратегия совместной разработки ВашСад

## Два проекта — одна система

| Репозиторий | Роль | Хостинг |
|-------------|------|---------|
| `vashsad-miniapp` (Next.js 16, TypeScript) | Веб-UI: каталог, дизайнер, полив, отзывы | Vercel |
| `vashsad-full` (Python aiogram 3) | Telegram Bot API: команды, FSM, AI-чат, фото-диагностика | Railway |

**Общая база данных:** Neon PostgreSQL — одна, разделяемая обоими проектами.

---

## Принцип разделения ответственности

```
Пользователь открывает Telegram
       │
       ▼
  Python бот (Railway) — единственная точка входа Bot API
  ├── /start        → приветствие + кнопка "🌿 Открыть ВашСад"
  ├── /plan         → FSM-диалог планирования участка
  ├── /order        → FSM оформления заявки
  ├── фото          → AI-диагностика через Claude Vision
  ├── текст         → AI-чат по садоводству
  └── кнопка Mini App → открывает Next.js приложение
               │
               ▼
         Next.js miniapp (Vercel)
         Полноценный веб-UI внутри Telegram
         ├── Каталог растений (169+)
         ├── PlantModal: отзывы, цены, закладки, комбинации
         ├── Дизайнер участка (AI)
         ├── Трекер полива
         ├── Профиль и статистика
         └── Все богатые UI-компоненты
               │
               ▼
         Neon PostgreSQL (общая БД)
         plants, users, bookmarks, reviews, combinations,
         chat_history, orders, diagnoses, user_plants...
```

**Telegram Bot API** обрабатывает только Python бот. Next.js webhook (`/api/telegram/webhook`) — заглушка.

---

## Правила синхронизации БД

Python бот создаёт таблицы через `_create_tables()` в `services/database.py`.
Next.js работает с теми же таблицами через `lib/db.ts` (Neon serverless).

**При изменении схемы:**
- Изменения делаются в `services/database.py` (Python бот)
- Next.js не создаёт таблицы сам — только читает/пишет
- После изменения схемы — перезапустить Python бот для применения `CREATE TABLE IF NOT EXISTS / ALTER TABLE`

**Критические пересечения таблиц:**

| Таблица | Владелец схемы | Кто пишет | Кто читает |
|---------|---------------|-----------|-----------|
| `users` | Python бот | Оба | Оба |
| `plants` | Next.js (миграции) | Next.js | Python бот (read-only) |
| `orders` | Python бот | Python бот | Next.js `/admin` |
| `chat_history` | Python бот | Python бот | Next.js профиль |
| `bookmarks` | Next.js | Next.js | — |
| `reviews` | Next.js | Next.js | — |

---

## Деплой

### Next.js → Vercel (автоматически)
Push в `main` → Vercel собирает и деплоит.
URL: `https://vashsad-miniapp-pi.vercel.app`

### Python бот → Railway
```bash
# Первый деплой
railway login
railway link  # привязать к проекту vashsad-bot
railway up

# Обновление
git push  # если настроен auto-deploy из GitHub
# или
railway up
```

**Env vars в Railway** (скопировать из Vercel):
```
TELEGRAM_BOT_TOKEN=
ANTHROPIC_API_KEY=
DATABASE_URL=          # тот же Neon URL что в Vercel
REDIS_URL=             # Upstash Redis URL (redis://...)
DESIGNER_TELEGRAM_ID=
DESIGNER_NAME=
DESIGNER_NAME_GEN=
MINI_APP_URL=https://vashsad-miniapp-pi.vercel.app
FREE_CHAT_LIMIT=10
FREE_PHOTO_LIMIT=3
FREE_PLANTS_LIMIT=3
```

---

## Workflow разработки

### Работа над ботом (Python)
1. Открыть сессию в `C:/Projects/vashsad-full`
2. Стартовый промпт: вставить содержимое `max-integration/PROMPT.md` (или написать свой)
3. Ссылаться на `docs/00_Backlog.md` для задач

### Работа над miniapp (Next.js)
1. Открыть сессию в `C:/Users/tsvetkov/vashsad-miniapp`
2. Claude читает `CLAUDE.md` → `AGENTS.md` автоматически

### Работа над обоими (типичный сценарий)
Если задача затрагивает оба проекта (например, новое поле в БД):
1. Сначала изменить схему в `services/database.py` (Python бот)
2. Затем использовать новое поле в Next.js API routes
3. Деплоить Python бот (`railway up`) → затем Next.js (`git push`)

---

## Следующие приоритетные задачи

### Python бот
- [ ] `TASK-001` выполнен — SQLite заменён на Neon PostgreSQL ✅ (в `services/database.py`)
- [ ] Задеплоить на Railway (первый деплой)
- [ ] Добавить приветственное фото маскота (`TASK-003`)
- [ ] FSM /plan — генерация плана участка (`TASK-002`)

### Next.js miniapp
- [ ] VAPID ключи → push-уведомления (`Task D`)
- [ ] Рефакторинг `app/page.tsx` 6000+ строк → `components/screens/` (`Block 4`)
- [ ] Реальные питомники в БД (`Task F`)

### Общие / интеграционные
- [ ] Единая схема таблицы `users`: добавить `push_subscription` из Next.js в схему Python бота
- [ ] Монорепо: перенести `vashsad-full/` в `vashsad-miniapp/bot/` (опционально, когда удобно)
