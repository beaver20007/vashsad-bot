"""
Абстрактный интерфейс платформы.
Реализуется отдельно для Telegram и MAX.
Бизнес-логика работает только с BotPlatform — не знает о конкретной платформе.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class UnifiedUser:
    """Унифицированная модель пользователя."""
    platform_id: str          # user_id в терминах платформы
    username: Optional[str]
    first_name: str
    last_name: Optional[str] = None
    language_code: Optional[str] = None
    platform: str = "unknown"  # "telegram" | "max"


@dataclass
class InlineButton:
    """Кнопка inline-клавиатуры."""
    text: str
    callback_data: str


@dataclass
class InlineKeyboard:
    """Разметка inline-клавиатуры (список рядов кнопок)."""
    rows: list[list[InlineButton]] = field(default_factory=list)

    def add_row(self, *buttons: InlineButton) -> "InlineKeyboard":
        self.rows.append(list(buttons))
        return self


@dataclass
class UnifiedMessage:
    """Входящее сообщение в унифицированном формате."""
    platform_id: str           # ID сообщения на платформе
    chat_id: str               # ID чата/диалога
    user: UnifiedUser
    text: Optional[str]
    platform: str = "unknown"


@dataclass
class UnifiedCallback:
    """Callback от нажатия inline-кнопки."""
    callback_id: str           # ID для ответа (answer_callback)
    chat_id: str
    message_id: str
    user: UnifiedUser
    data: str                  # callback_data
    platform: str = "unknown"


class BotPlatform(ABC):
    """
    Абстрактный транспортный адаптер.

    Реализации:
    - TelegramPlatform (src/platforms/telegram.py)
    - MaxPlatform (src/platforms/max_platform.py)
    """

    @abstractmethod
    async def send_message(
        self,
        chat_id: str,
        text: str,
        keyboard: Optional[InlineKeyboard] = None,
        parse_mode: Optional[str] = None,
    ) -> str:
        """Отправить текстовое сообщение. Возвращает ID сообщения."""
        ...

    @abstractmethod
    async def edit_message(
        self,
        chat_id: str,
        message_id: str,
        text: str,
        keyboard: Optional[InlineKeyboard] = None,
    ) -> None:
        """Редактировать существующее сообщение."""
        ...

    @abstractmethod
    async def answer_callback(
        self,
        callback_id: str,
        text: Optional[str] = None,
        show_alert: bool = False,
    ) -> None:
        """Ответить на callback (убрать часики у кнопки)."""
        ...

    @abstractmethod
    async def send_document(
        self,
        chat_id: str,
        file_path: str,
        caption: Optional[str] = None,
    ) -> str:
        """Отправить файл. Возвращает ID сообщения."""
        ...

    @abstractmethod
    async def send_photo(
        self,
        chat_id: str,
        file_path: str,
        caption: Optional[str] = None,
    ) -> str:
        """Отправить фото. Возвращает ID сообщения."""
        ...

    @abstractmethod
    async def delete_message(
        self,
        chat_id: str,
        message_id: str,
    ) -> bool:
        """Удалить сообщение. Возвращает успех."""
        ...
