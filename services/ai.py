"""AI-сервис ВашСад Бот — обёртка над Anthropic API"""
import logging

import aiohttp

from config import ANTHROPIC_API_KEY, ANTHROPIC_MAX_TOKENS, ANTHROPIC_MODEL
from services import bot_texts

log = logging.getLogger(__name__)

async def ask_claude(messages: list, system: str = None) -> str:
    """Отправить запрос к Claude API и получить ответ"""
    if not ANTHROPIC_API_KEY:
        return (
            "⚠️ AI-консультация временно недоступна.\n\n"
            "Для получения совета напишите напрямую дизайнеру — "
            "нажмите кнопку «Заказать проект»."
        )

    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }

    payload = {
        "model": ANTHROPIC_MODEL,
        "max_tokens": ANTHROPIC_MAX_TOKENS,
        "system": system or bot_texts.get("system_prompt.chat")["text"],
        "messages": messages,
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.anthropic.com/v1/messages",
                headers=headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status != 200:
                    err = await resp.text()
                    log.error(f"Claude API error {resp.status}: {err}")
                    return "❌ Ошибка AI. Попробуйте позже или нажмите «Заказать проект» для связи с дизайнером."

                data = await resp.json()
                return data["content"][0]["text"]

    except aiohttp.ClientTimeout:
        return "⏳ Запрос занял слишком много времени. Попробуйте ещё раз."
    except Exception as e:
        log.error(f"Claude API exception: {e}")
        return "❌ Произошла ошибка. Попробуйте позже."


async def ask_claude_with_image(image_bytes: bytes, mime_type: str, question: str) -> str:
    """Анализ изображения растения через Claude Vision"""
    if not ANTHROPIC_API_KEY:
        return (
            "⚠️ Фото-диагностика временно недоступна.\n\n"
            "Отправьте фото дизайнеру — нажмите кнопку «Заказать проект»."
        )

    import base64
    image_b64 = base64.standard_b64encode(image_bytes).decode("utf-8")

    system = bot_texts.get("system_prompt.vision")["text"]

    messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": mime_type,
                        "data": image_b64,
                    },
                },
                {"type": "text", "text": question or "Что не так с этим растением? Поставь диагноз и дай рекомендации."},
            ],
        }
    ]

    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }

    payload = {
        "model": ANTHROPIC_MODEL,
        "max_tokens": ANTHROPIC_MAX_TOKENS,
        "system": system,
        "messages": messages,
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.anthropic.com/v1/messages",
                headers=headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=45),
            ) as resp:
                if resp.status != 200:
                    err = await resp.text()
                    log.error(f"Claude Vision error {resp.status}: {err}")
                    return "❌ Не удалось проанализировать фото. Попробуйте ещё раз."

                data = await resp.json()
                return data["content"][0]["text"]

    except Exception as e:
        log.error(f"Claude Vision exception: {e}")
        return "❌ Ошибка при анализе фото. Попробуйте позже."


async def generate_garden_plan(params: dict) -> str:
    prompt = f"""Составь текстовый план участка для природного сада:
Площадь: {params.get('area')}
Регион: {params.get('region', 'Средняя полоса России')}
Что есть: {params.get('existing')}
Стиль: {params.get('style')}
Пожелания: {params.get('wishes')}

Опиши: зонирование, 5-7 растений, с чего начать.
В конце предложи нажать кнопку «Заказать проект»."""
    return await ask_claude([{"role": "user", "content": prompt}])


async def select_plants(params: dict) -> str:
    prompt = f"""Подбери растения для сада:
Регион: {params.get('region', 'Средняя полоса России')}
Тип: {params.get('plant_type')}
Освещение: {params.get('light')}

Дай список 8-10 растений с описанием.
В конце предложи нажать кнопку «Заказать проект» для профессионального подбора."""
    return await ask_claude([{"role": "user", "content": prompt}])
