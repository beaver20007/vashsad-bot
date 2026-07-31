"""
Реализация BotPlatform для мессенджера MAX.

Документация: https://dev.max.ru/docs-api
Base URL: https://platform-api.max.ru
Auth: заголовок Authorization: <token>

⚠️ ВАЖНО: Документация MAX расходится с реальностью.
Все ответы API логируются для дебага.
"""
import json
from pathlib import Path
from typing import Optional

import httpx
from loguru import logger

from src.core.platform import (
    BotPlatform,
    InlineButton,
    InlineKeyboard,
    UnifiedCallback,
    UnifiedMessage,
    UnifiedUser,
)

MAX_API_BASE = "https://platform-api.max.ru"


class MaxPlatform(BotPlatform):
    """
    Транспортный адаптер для MAX Bot API.

    Использование:
        platform = MaxPlatform(token=os.environ["MAX_BOT_TOKEN_VASHSAD"])
        await platform.send_message(chat_id="123", text="Привет!")
    """

    def __init__(self, token: str) -> None:
        self.token = token
        self._headers = {
            "Authorization": token,
            "Content-Type": "application/json",
        }
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=MAX_API_BASE,
                headers=self._headers,
                timeout=10.0,
            )
        return self._client

    async def _request(
        self,
        method: str,
        path: str,
        **kwargs,
    ) -> dict:
        """Выполнить запрос к MAX API с логированием."""
        client = await self._get_client()
        response = await client.request(method, path, **kwargs)

        # Логируем ВСЁ — документация врёт, без логов дебаг невозможен
        logger.debug(
            "MAX API {method} {path} → {status}",
            method=method,
            path=path,
            status=response.status_code,
        )
        logger.debug("MAX API response: {body}", body=response.text[:2000])

        response.raise_for_status()
        return response.json()

    # ─── Парсинг входящих событий ────────────────────────────────────────────

    @staticmethod
    def parse_webhook(payload: dict) -> Optional[UnifiedMessage | UnifiedCallback]:
        """
        Разобрать webhook payload от MAX.

        ⚠️ Реальная структура (не как в доке):
        {
          "update_type": "message_created",
          "user_locale": "ru",
          "message": { ... }   # или другой ключ
        }
        """
        logger.debug("MAX webhook raw: {payload}", payload=json.dumps(payload, ensure_ascii=False))

        update_type = payload.get("update_type", "")

        if update_type == "message_created":
            msg = payload.get("message", {})
            sender = msg.get("sender", {})
            user = UnifiedUser(
                platform_id=str(sender.get("user_id", "")),
                username=sender.get("username"),
                first_name=sender.get("name", ""),
                language_code=payload.get("user_locale"),
                platform="max",
            )
            return UnifiedMessage(
                platform_id=str(msg.get("mid", "")),
                chat_id=str(msg.get("recipient", {}).get("chat_id", "")),
                user=user,
                text=msg.get("body", {}).get("text"),
                platform="max",
            )

        elif update_type == "message_callback":
            cb = payload.get("callback", {})
            sender = cb.get("user", {})
            user = UnifiedUser(
                platform_id=str(sender.get("user_id", "")),
                username=sender.get("username"),
                first_name=sender.get("name", ""),
                language_code=payload.get("user_locale"),
                platform="max",
            )
            return UnifiedCallback(
                callback_id=str(cb.get("callback_id", "")),
                chat_id=str(cb.get("message", {}).get("recipient", {}).get("chat_id", "")),
                message_id=str(cb.get("message", {}).get("mid", "")),
                user=user,
                data=cb.get("payload", ""),
                platform="max",
            )

        elif update_type == "bot_started":
            # Пользователь нажал "Начать" / открыл бота впервые
            user_data = payload.get("user", {})
            user = UnifiedUser(
                platform_id=str(user_data.get("user_id", "")),
                username=user_data.get("username"),
                first_name=user_data.get("name", ""),
                language_code=payload.get("user_locale"),
                platform="max",
            )
            chat_id = str(payload.get("chat_id", user_data.get("user_id", "")))
            return UnifiedMessage(
                platform_id="bot_started",
                chat_id=chat_id,
                user=user,
                text="/start",
                platform="max",
            )

        logger.warning("MAX: неизвестный update_type={t}", t=update_type)
        return None

    # ─── Конвертация клавиатуры ───────────────────────────────────────────────

    @staticmethod
    def _keyboard_to_max(keyboard: InlineKeyboard) -> list:
        """Конвертировать InlineKeyboard в формат MAX API."""
        buttons = []
        for row in keyboard.rows:
            max_row = []
            for btn in row:
                max_row.append({
                    "type": "callback",
                    "text": btn.text,
                    "payload": btn.callback_data,
                })
            buttons.append(max_row)
        return buttons

    # ─── Реализация BotPlatform ───────────────────────────────────────────────

    async def send_message(
        self,
        chat_id: str,
        text: str,
        keyboard: Optional[InlineKeyboard] = None,
        parse_mode: Optional[str] = None,
    ) -> str:
        body: dict = {
            "recipient": {"chat_id": int(chat_id)},
            "type": "default",
            "body": {"text": text},
        }
        if keyboard:
            body["attachments"] = [{
                "type": "inline_keyboard",
                "payload": {"buttons": self._keyboard_to_max(keyboard)},
            }]

        result = await self._request("POST", "/messages", json=body)
        return str(result.get("message", {}).get("mid", ""))

    async def edit_message(
        self,
        chat_id: str,
        message_id: str,
        text: str,
        keyboard: Optional[InlineKeyboard] = None,
    ) -> None:
        body: dict = {"body": {"text": text}}
        if keyboard:
            body["attachments"] = [{
                "type": "inline_keyboard",
                "payload": {"buttons": self._keyboard_to_max(keyboard)},
            }]
        await self._request("PUT", f"/messages/{message_id}", json=body)

    async def answer_callback(
        self,
        callback_id: str,
        text: Optional[str] = None,
        show_alert: bool = False,
    ) -> None:
        body: dict = {"callback_id": callback_id}
        if text:
            body["message"] = {"text": text}
        await self._request("POST", "/answers", json=body)

    async def send_document(
        self,
        chat_id: str,
        file_path: str,
        caption: Optional[str] = None,
    ) -> str:
        # Шаг 1: загрузить файл
        file_token = await self._upload_file(file_path, "file")
        # Шаг 2: отправить сообщение с вложением
        body: dict = {
            "recipient": {"chat_id": int(chat_id)},
            "type": "default",
            "attachments": [{"type": "file", "payload": {"token": file_token}}],
        }
        if caption:
            body["body"] = {"text": caption}
        result = await self._request("POST", "/messages", json=body)
        return str(result.get("message", {}).get("mid", ""))

    async def send_photo(
        self,
        chat_id: str,
        file_path: str,
        caption: Optional[str] = None,
    ) -> str:
        file_token = await self._upload_file(file_path, "image")
        body: dict = {
            "recipient": {"chat_id": int(chat_id)},
            "type": "default",
            "attachments": [{"type": "image", "payload": {"token": file_token}}],
        }
        if caption:
            body["body"] = {"text": caption}
        result = await self._request("POST", "/messages", json=body)
        return str(result.get("message", {}).get("mid", ""))

    async def delete_message(
        self,
        chat_id: str,
        message_id: str,
    ) -> bool:
        try:
            await self._request("DELETE", f"/messages/{message_id}")
            return True
        except httpx.HTTPStatusError as e:
            # В MAX удаление нестабильно — логируем, не падаем
            logger.warning("MAX delete_message failed: {e}", e=e)
            return False

    # ─── Загрузка файлов ─────────────────────────────────────────────────────

    async def _upload_file(self, file_path: str, upload_type: str) -> str:
        """Загрузить файл в MAX, вернуть token для последующей отправки."""
        path = Path(file_path)
        client = await self._get_client()

        with path.open("rb") as f:
            files = {"file": (path.name, f)}
            # Загрузка — multipart, без json заголовка
            response = await client.post(
                f"/uploads?type={upload_type}",
                files=files,
                headers={"Authorization": self.token},
            )
            response.raise_for_status()
            data = response.json()
            logger.debug("MAX upload response: {data}", data=data)
            return data.get("token", "")

    # ─── Управление webhook ──────────────────────────────────────────────────

    async def set_webhook(self, url: str) -> None:
        """Подписаться на события через webhook. URL должен быть HTTPS."""
        await self._request("POST", "/subscriptions", json={"url": url})
        logger.info("MAX webhook установлен: {url}", url=url)

    async def delete_webhook(self) -> None:
        """Отписаться от webhook (нужно перед Long Polling)."""
        await self._request("DELETE", "/subscriptions")

    async def get_me(self) -> dict:
        """Получить информацию о боте."""
        return await self._request("GET", "/me")

    async def close(self) -> None:
        """Закрыть HTTP сессию."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
