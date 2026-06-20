# Мониторинг доступности — ВашСад Бот

## 1. UptimeRobot (бесплатный тариф)

### Регистрация и настройка монитора

1. Зарегистрируйтесь на [uptimerobot.com](https://uptimerobot.com)
2. Нажмите **+ Add New Monitor**
3. Заполните параметры:

| Параметр | Значение |
|----------|----------|
| Monitor Type | HTTP(S) |
| Friendly Name | VashSad Miniapp Health |
| URL | `https://YOUR_DOMAIN/api/health` |
| Monitoring Interval | 5 minutes |
| HTTP Method | GET |

### Условия оповещения

- **Status code**: alert if != 200
- **Keyword alert**: Add keyword monitor → keyword `"down"` → Alert when keyword exists

Для keyword-мониторинга создайте второй монитор того же URL с типом **Keyword** и укажите:
- Keyword: `down`
- Alert when: keyword exists

### Оповещения по Email

1. Перейдите в **My Settings → Alert Contacts**
2. Нажмите **Add Alert Contact**
3. Тип: **E-mail**, укажите адрес дизайнера
4. Подтвердите адрес по письму
5. Привяжите контакт к монитору

### Оповещения в Telegram

UptimeRobot поддерживает Telegram-оповещения через интеграцию:

1. В **Alert Contacts** нажмите **Add Alert Contact**
2. Тип: **Telegram**
3. Нажмите **Click here to get your Chat ID** — откроется @UptimeRobot_bot
4. Напишите боту `/start`, он вернёт ваш Chat ID
5. Вставьте Chat ID в форму, сохраните
6. Добавьте этот контакт к монитору

Альтернатива через webhook:
1. Тип контакта: **Webhook**
2. URL: `https://api.telegram.org/bot<YOUR_BOT_TOKEN>/sendMessage`
3. Method: POST
4. Post Value:
```json
{
  "chat_id": "DESIGNER_TELEGRAM_ID",
  "text": "*[UptimeRobot]* $monitorFriendlyName is $alertTypeFriendlyName\nURL: $monitorURL",
  "parse_mode": "Markdown"
}
```

### Страница статуса (бесплатно)

UptimeRobot предоставляет публичную страницу статуса:
1. **My Settings → Status Pages → Create Status Page**
2. Добавьте мониторы
3. Получите публичный URL вида `https://stats.uptimerobot.com/XXXXX`

---

## 2. BetterStack Uptime (альтернатива)

### Настройка монитора

1. Зарегистрируйтесь на [betterstack.com/uptime](https://betterstack.com/uptime)
2. **New Monitor** → тип **HTTPS**
3. Параметры:

| Параметр | Значение |
|----------|----------|
| URL | `https://YOUR_DOMAIN/api/health` |
| Check frequency | 3 minutes (на бесплатном тарифе — 3 мин) |
| Expected HTTP status | 200 |
| Request timeout | 10 seconds |
| Regions | Frankfurt (ближайший к РФ) |

### On-call и инциденты

1. **On-Call Schedules** → создайте расписание дежурства
2. **Escalation Policies** → настройте цепочку оповещений:
   - 0 мин: Email
   - 5 мин: SMS (если не подтверждено)
   - 10 мин: Phone call
3. Интеграции: Telegram, Slack, PagerDuty, OpsGenie

### Интеграция с Telegram

1. **Integrations → Telegram**
2. Следуйте инструкции: добавьте @BetterStackBot в нужный чат
3. Отправьте команду для привязки
4. Выберите события: Monitor down, Monitor up, SSL expiry

### Публичная страница статуса

BetterStack предоставляет кастомизируемую страницу статуса:
1. **Status Pages → New Status Page**
2. Укажите домен (например, `status.yourdomain.ru`)
3. Добавьте мониторы
4. Настройте внешний вид в корпоративном стиле

---

## 3. Self-hosted мониторинг (встроенный в бот)

### Self-ping job (уже добавлен в services/scheduler.py)

Каждые 10 минут бот автоматически проверяет `/api/health` miniapp и отправляет алерт дизайнеру в Telegram при сбое.

Функция `self_ping_check` в `services/scheduler.py`:
- GET `http://localhost:3000/api/health`
- Таймаут: 10 секунд
- При HTTP != 200: сообщение дизайнеру с кодом ответа
- При недоступности (исключение): сообщение "Miniapp не отвечает!"

Задача зарегистрирована с ID `self_ping` в `setup_scheduler`.

### Требования

Убедитесь, что `aiohttp` установлен:
```
pip install aiohttp
```
Уже должен быть в зависимостях (используется в других местах).

### Endpoint /api/health

Убедитесь, что `vashsad-miniapp/app/api/health/route.ts` возвращает:
```json
{
  "status": "ok",
  "services": {
    "database": "ok",
    "redis": "ok"
  },
  "timestamp": "2024-01-01T00:00:00.000Z"
}
```
При ошибке БД или Redis поле `status` должно содержать `"down"` или `"degraded"`, HTTP-статус должен быть != 200.

---

## Итоговая рекомендация

| Уровень | Инструмент | Стоимость |
|---------|-----------|-----------|
| Минимум | UptimeRobot Free | Бесплатно |
| Оптимально | UptimeRobot Free + self_ping в боте | Бесплатно |
| Продвинутый | BetterStack + публичная страница статуса | Бесплатно / $24/мес |

**Для старта** достаточно UptimeRobot (бесплатный тариф — до 50 мониторов, проверка каждые 5 минут) плюс встроенный self-ping в боте.
