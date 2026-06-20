"""Фаза 4: Inline-режим — @vashsad_bot [вопрос] в любом чате"""
import logging
from aiogram import Router
from aiogram.types import (
    InlineQuery, InlineQueryResultArticle,
    InputTextMessageContent,
)
from services.ai import ask_claude

router = Router()
log = logging.getLogger(__name__)

INLINE_SYSTEM = (
    "Ты — краткий AI-помощник по садоводству. "
    "Отвечай одним абзацем (3–4 предложения), только по теме садоводства и ландшафтного дизайна. "
    "Заканчивай ответ советом или призывом. Язык — русский."
)

QUICK_TIPS = [
    ("🌹 Обрезка роз",          "Обрезайте розы до 3-й наружной почки. Весной — санитарная обрезка (удалить мёртвое), осенью — формирующая. Используйте острый секатор и обрабатывайте срезы садовым варом."),
    ("💧 Правила полива",       "Поливайте редко, но обильно — раз в 3–5 дней в засуху. Утренний полив снижает риск грибка. Мульча сохраняет влагу и сокращает частоту полива вдвое."),
    ("🌱 Первая подкормка",     "Азотные удобрения (мочевина, аммиачная селитра) вносите в апреле–мае для активного роста. Фосфорно-калийные — летом и осенью для укрепления корней и зимостойкости."),
    ("🍂 Подготовка к зиме",    "Укройте розы и теплолюбивые многолетники до первых устойчивых морозов. Используйте лапник, агроволокно или специальные мешки. Не укрывайте при оттепели — выпреют."),
]


@router.inline_query()
async def handle_inline(query: InlineQuery):
    q = query.query.strip()

    # Быстрые подсказки при пустом запросе
    if not q:
        results = [
            InlineQueryResultArticle(
                id=str(i),
                title=title,
                description=tip[:80] + "...",
                input_message_content=InputTextMessageContent(
                    message_text=f"🌿 <b>{title}</b>\n\n{tip}\n\n<i>— ВашСад AI</i>",
                    parse_mode="HTML",
                ),
            )
            for i, (title, tip) in enumerate(QUICK_TIPS)
        ]
        await query.answer(results, cache_time=300)
        return

    # AI-ответ на конкретный вопрос
    try:
        answer = await ask_claude(
            messages=[{"role": "user", "content": q}],
            system=INLINE_SYSTEM,
            max_tokens=300,
        )
    except Exception as e:
        log.warning("Inline AI error: %s", e)
        answer = "Не удалось получить ответ. Напишите боту напрямую!"

    result = InlineQueryResultArticle(
        id="ai_answer",
        title=f"🌿 {q[:40]}",
        description=answer[:100] + ("..." if len(answer) > 100 else ""),
        input_message_content=InputTextMessageContent(
            message_text=f"🌿 <b>{q}</b>\n\n{answer}\n\n<i>— ВашСад AI (@vashsad_bot)</i>",
            parse_mode="HTML",
        ),
    )
    await query.answer([result], cache_time=60)
