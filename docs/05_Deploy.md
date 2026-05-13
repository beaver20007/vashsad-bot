# Деплой ВашСад Бот на VPS
# Пошаговая инструкция запуска 24/7

---

## Шаг 1 — Выбор VPS

Рекомендуемые провайдеры (РФ):
- **Timeweb** — от 199 ₽/мес, хорошая поддержка
- **Beget** — от 300 ₽/мес
- **Selectel** — от 350 ₽/мес

Минимальная конфигурация:
- CPU: 1 vCPU
- RAM: 1 GB
- SSD: 10 GB
- OS: Ubuntu 22.04 LTS

---

## Шаг 2 — Первичная настройка сервера

```bash
# Подключение (замени IP на свой)
ssh root@YOUR_SERVER_IP

# Обновление системы
apt update && apt upgrade -y

# Установка Python 3.12
apt install -y python3.12 python3.12-venv python3-pip git

# Установка зависимостей
apt install -y curl wget nano

# Создание пользователя для бота
adduser vashsad --disabled-password --gecos ""
su - vashsad
```

---

## Шаг 3 — Загрузка кода

```bash
# На сервере под пользователем vashsad
cd ~
git clone https://github.com/YOUR_USERNAME/vashsad-bot.git
# или загрузи архив через scp:
# scp vashsad-bot-mvp.zip root@YOUR_IP:/home/vashsad/
# unzip vashsad-bot-mvp.zip

cd vashsad-bot  # или vashsad/

# Создать виртуальное окружение
python3.12 -m venv venv
source venv/bin/activate

# Установить зависимости
pip install aiogram anthropic python-dotenv aiohttp
```

---

## Шаг 4 — Настройка .env

```bash
cp .env.example .env
nano .env
```

Заполнить:
```bash
TELEGRAM_BOT_TOKEN=7xxx:AAA-xxxx
ANTHROPIC_API_KEY=sk-ant-api03-xxxx
DESIGNER_TELEGRAM_ID=123456789   # Узнать у @userinfobot
DESIGNER_NAME=Ваше Имя
FREE_CHAT_LIMIT=10
FREE_PHOTO_LIMIT=3
FREE_PLANTS_LIMIT=3
```

---

## Шаг 5 — Systemd сервис (автозапуск)

```bash
# Выйти из пользователя vashsad
exit

# Создать systemd unit
nano /etc/systemd/system/vashsad-bot.service
```

Содержимое файла:
```ini
[Unit]
Description=VashSad Telegram Bot
After=network.target
Wants=network-online.target

[Service]
Type=simple
User=vashsad
WorkingDirectory=/home/vashsad/vashsad-bot
Environment=PATH=/home/vashsad/vashsad-bot/venv/bin
ExecStart=/home/vashsad/vashsad-bot/venv/bin/python bot.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

```bash
# Активировать и запустить
systemctl daemon-reload
systemctl enable vashsad-bot
systemctl start vashsad-bot

# Проверить статус
systemctl status vashsad-bot

# Смотреть логи в реальном времени
journalctl -u vashsad-bot -f
```

---

## Шаг 6 — Обновление кода

```bash
# На сервере
su - vashsad
cd vashsad-bot
git pull origin main
source venv/bin/activate
pip install -r requirements.txt  # если изменились зависимости

# Перезапустить бота
exit
systemctl restart vashsad-bot
systemctl status vashsad-bot
```

---

## Шаг 7 — Мониторинг

```bash
# Статус
systemctl status vashsad-bot

# Логи последних 100 строк
journalctl -u vashsad-bot -n 100

# Логи в реальном времени
journalctl -u vashsad-bot -f

# Место на диске
df -h

# Память
free -h
```

---

## requirements.txt

```txt
aiogram==3.7.0
anthropic>=0.25.0
python-dotenv>=1.0.0
aiohttp>=3.9.0
```

---

## Быстрая проверка что бот работает

1. Открой Telegram
2. Найди своего бота по username
3. Напиши `/start`
4. Должно прийти welcome-сообщение с меню

Если не отвечает:
```bash
journalctl -u vashsad-bot -n 50
# Смотри ошибки — обычно проблема в .env (неверный токен или API ключ)
```
