"""
services/i18n.py
Строки интерфейса из content_strings (namespace bot_text, ключ ``i18n``,
структура {язык: {ключ: текст}}) через services/bot_texts.py.
"""
from services import bot_texts


def t(key: str, lang: str = "ru") -> str:
    """Return translated string for key in the given language.

    Falls back to 'ru' if the language or key is not found.
    """
    strings = bot_texts.get("i18n")
    lang = lang if lang in strings else "ru"
    return strings[lang].get(key) or strings["ru"].get(key, key)
