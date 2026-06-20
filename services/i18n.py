"""
services/i18n.py
Basic internationalization support for the ВашСад bot.
"""

STRINGS: dict[str, dict[str, str]] = {
    "ru": {
        "welcome": (
            "🌿 <b>Добро пожаловать в {bot_name}!</b>\n\n"
            "Я — AI-помощник {designer_name}, дипломированного ландшафтного дизайнера.\n\n"
            "Помогу вам:\n"
            "🗺 Создать план вашего участка\n"
            "🌱 Подобрать растения под ваш климат и стиль\n"
            "📸 Определить болезнь растения по фото\n"
            "📅 Составить календарь ухода за садом\n"
            "💬 Ответить на любой вопрос по садоводству\n\n"
            "<b>Выберите, с чего начнём 👇</b>"
        ),
        "menu_hint": "Используйте кнопки быстрого доступа 👇",
        "chat_limit_reached": (
            "⚠️ Вы исчерпали лимит бесплатных сообщений.\n"
            "Оформите подписку <b>Сад Про</b> для безлимитного доступа."
        ),
        "subscription_required": (
            "⭐ Эта функция доступна в подписке <b>Сад Про</b>.\n"
            "Нажмите кнопку ниже, чтобы оформить подписку."
        ),
        "order_started": "📋 Оформление заявки на услугу. Выберите тип услуги:",
        "booking_started": "📅 Запись на консультацию. Укажите удобное время:",
        "plants_started": "🌱 Подбор растений. Расскажите об условиях вашего участка:",
        "success_subscribed": "✅ Подписка <b>Сад Про</b> успешно оформлена! Пользуйтесь без ограничений 🌿",
        "error_generic": "❌ Что-то пошло не так. Попробуйте ещё раз или напишите в поддержку.",
    },
    "en": {
        "welcome": (
            "🌿 <b>Welcome to {bot_name}!</b>\n\n"
            "I am the AI assistant of {designer_name}, a certified landscape designer.\n\n"
            "I can help you:\n"
            "🗺 Create a plan for your plot\n"
            "🌱 Select plants suited to your climate and style\n"
            "📸 Identify plant diseases from photos\n"
            "📅 Build a garden care calendar\n"
            "💬 Answer any gardening question\n\n"
            "<b>Choose where to start 👇</b>"
        ),
        "menu_hint": "Use the quick-access buttons below 👇",
        "chat_limit_reached": (
            "⚠️ You have used all your free messages.\n"
            "Subscribe to <b>Garden Pro</b> for unlimited access."
        ),
        "subscription_required": (
            "⭐ This feature is available with the <b>Garden Pro</b> subscription.\n"
            "Press the button below to subscribe."
        ),
        "order_started": "📋 Starting your service request. Please choose a service type:",
        "booking_started": "📅 Booking a consultation. Please specify a convenient time:",
        "plants_started": "🌱 Plant selection. Tell us about your plot conditions:",
        "success_subscribed": "✅ <b>Garden Pro</b> subscription activated! Enjoy unlimited access 🌿",
        "error_generic": "❌ Something went wrong. Please try again or contact support.",
    },
}


def t(key: str, lang: str = "ru") -> str:
    """Return translated string for key in the given language.

    Falls back to 'ru' if the language or key is not found.
    """
    lang = lang if lang in STRINGS else "ru"
    return STRINGS[lang].get(key) or STRINGS["ru"].get(key, key)
