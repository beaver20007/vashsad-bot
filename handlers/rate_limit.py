from aiogram import BaseMiddleware
from aiogram.types import Message
from collections import defaultdict
import time

class RateLimitMiddleware(BaseMiddleware):
    def __init__(self, limit=20, window=60):
        self.limit = limit  # messages per window
        self.window = window  # seconds
        self.user_timestamps = defaultdict(list)

    async def __call__(self, handler, event, data):
        if not isinstance(event, Message):
            return await handler(event, data)

        user_id = event.from_user.id
        now = time.time()

        # Clean old timestamps
        self.user_timestamps[user_id] = [
            t for t in self.user_timestamps[user_id]
            if now - t < self.window
        ]

        if len(self.user_timestamps[user_id]) >= self.limit:
            await event.answer("⚠️ Слишком много сообщений. Подождите немного.")
            return

        self.user_timestamps[user_id].append(now)
        return await handler(event, data)
