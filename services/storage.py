"""
Хранилище пользователей ВашСад Бот (in-memory MVP).
В production заменить на PostgreSQL / SQLite.
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class User:
    telegram_id: int
    username: Optional[str] = None
    first_name: Optional[str] = None
    region: Optional[str] = None
    is_subscribed: bool = False
    chat_count: int = 0        # AI-сообщений за месяц
    photo_count: int = 0       # Фото-диагностик за месяц
    plants_count: int = 0      # Запросов подбора за месяц
    chat_history: list = field(default_factory=list)  # История для AI
    created_at: datetime = field(default_factory=datetime.now)


# Глобальное хранилище (заменить на БД в production)
_users: dict[int, User] = {}


def get_user(telegram_id: int) -> Optional[User]:
    return _users.get(telegram_id)


def get_or_create_user(telegram_id: int, username: str = None, first_name: str = None) -> User:
    if telegram_id not in _users:
        _users[telegram_id] = User(
            telegram_id=telegram_id,
            username=username,
            first_name=first_name,
        )
    return _users[telegram_id]


def update_user(user: User):
    _users[user.telegram_id] = user


def can_use_chat(user: User, limit: int) -> bool:
    return user.is_subscribed or user.chat_count < limit


def can_use_photo(user: User, limit: int) -> bool:
    return user.is_subscribed or user.photo_count < limit


def can_use_plants(user: User, limit: int) -> bool:
    return user.is_subscribed or user.plants_count < limit


def add_message_to_history(user: User, role: str, content: str, max_history: int = 10):
    """Добавить сообщение в историю чата для контекста AI"""
    user.chat_history.append({"role": role, "content": content})
    # Держим только последние N сообщений
    if len(user.chat_history) > max_history * 2:
        user.chat_history = user.chat_history[-(max_history * 2):]
    update_user(user)
