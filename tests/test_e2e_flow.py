"""
tests/test_e2e_flow.py
End-to-end integration-style tests for the VashSad Telegram bot.

Verifies complete user journeys using mocked Telegram API and Claude API.
Uses pytest + pytest-asyncio + unittest.mock.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pytest
import pytest_asyncio

# ---------------------------------------------------------------------------
# Helpers / stubs
# ---------------------------------------------------------------------------

def _make_user_dataclass(**kwargs):
    """Return a User-like object (dataclass substitute) for mocking."""
    from dataclasses import dataclass, field

    @dataclass
    class _User:
        telegram_id: int = 123456789
        username: str | None = "testuser"
        first_name: str | None = "Test"
        region: str | None = None
        is_subscribed: bool = False
        chat_count: int = 0
        photo_count: int = 0
        plants_count: int = 0
        plot_size: float | None = None
        chat_history: list = field(default_factory=list)
        created_at: datetime = field(default_factory=datetime.now)
        subscription_expires_at: datetime | None = None
        referral_code: str | None = None
        referred_by: int | None = None
        bonus_messages: int = 0
        lang: str = "ru"
        pdn_consent_at: datetime | None = field(default_factory=datetime.now)

    user = _User()
    for k, v in kwargs.items():
        setattr(user, k, v)
    return user


def _make_message(
    text: str = "/start",
    user_id: int = 123456789,
    username: str = "testuser",
    first_name: str = "Test",
    language_code: str = "ru",
    date: datetime | None = None,
) -> MagicMock:
    """Build a minimal aiogram Message mock."""
    msg = MagicMock()
    msg.text = text
    msg.chat = MagicMock()
    msg.chat.id = user_id

    from_user = MagicMock()
    from_user.id = user_id
    from_user.username = username
    from_user.first_name = first_name
    from_user.language_code = language_code
    msg.from_user = from_user

    msg.date = date or datetime.utcnow()

    # Async methods
    msg.answer = AsyncMock()
    msg.answer_photo = AsyncMock()
    msg.bot = MagicMock()
    msg.bot.send_chat_action = AsyncMock()
    return msg


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_pool():
    """Return a mock asyncpg connection pool."""
    pool = MagicMock()
    conn = AsyncMock()
    pool.acquire = MagicMock(return_value=AsyncMock(
        __aenter__=AsyncMock(return_value=conn),
        __aexit__=AsyncMock(return_value=False),
    ))
    return pool, conn


@pytest.fixture
def new_user():
    return _make_user_dataclass(chat_count=0, referral_code=None)


@pytest.fixture
def limited_user():
    """User who has used up all FREE_CHAT_LIMIT messages."""
    return _make_user_dataclass(chat_count=10, bonus_messages=0)


# ---------------------------------------------------------------------------
# TestBotFlow
# ---------------------------------------------------------------------------

class TestBotFlow:
    """Integration-style tests for the complete user journey."""

    # ------------------------------------------------------------------ #
    # 1. /start flow                                                       #
    # ------------------------------------------------------------------ #

    @pytest.mark.asyncio
    async def test_start_flow(self, new_user):
        """
        Simulate /start for a new user.
        Verify:
          - get_or_create_user is called with correct telegram_id
          - A welcome message (or photo) is sent with an inline keyboard
          - A reply-keyboard hint is sent afterward
          - referral_code can be generated for the user
        """
        message = _make_message(text="/start", user_id=111222333)
        message.from_user.id = 111222333

        new_user.telegram_id = 111222333
        new_user.first_name = "Test"

        with (
            patch("handlers.start.get_or_create_user", new_callable=AsyncMock, return_value=new_user) as mock_get_user,
            patch("handlers.start.insert_analytics_event", new_callable=AsyncMock),
            patch("handlers.start.maybe_start_onboarding", new_callable=AsyncMock),
            patch("handlers.start.WELCOME_IMAGE_URL", ""),
            patch("handlers.start.t", side_effect=lambda key, lang: "{bot_name} {designer_name}" if key.startswith("welcome") else "Hint"),
        ):
            from handlers.start import cmd_start
            state_mock = AsyncMock()
            state_mock.set_state = AsyncMock()

            await cmd_start(message, state_mock)

        # get_or_create_user must have been called
        mock_get_user.assert_called_once_with(
            111222333,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
            language_code=message.from_user.language_code,
        )

        # At least two answer calls: welcome + menu hint
        assert message.answer.call_count >= 2, (
            "Expected at least 2 answer() calls (welcome + keyboard hint)"
        )

        # First call should carry an InlineKeyboardMarkup
        first_call_kwargs = message.answer.call_args_list[0].kwargs
        assert "reply_markup" in first_call_kwargs, "Welcome message should include reply_markup"

        # Referral code can be generated (tested separately in test_referral_code)
        from services.database import _make_referral_code
        code = _make_referral_code(111222333)
        assert code.startswith("REF"), "Referral code must start with REF"

    # ------------------------------------------------------------------ #
    # 1b. /start — 152-ФЗ: без согласия на ПДн дальше не пускаем           #
    # ------------------------------------------------------------------ #

    @pytest.mark.asyncio
    async def test_start_blocks_without_pdn_consent(self, new_user):
        """A user who has never confirmed ПДн-consent must see only the
        consent screen on /start — no welcome text, no menu hint."""
        new_user.pdn_consent_at = None
        message = _make_message(text="/start", user_id=555666777)
        message.from_user.id = 555666777

        with (
            patch("handlers.start.get_or_create_user", new_callable=AsyncMock, return_value=new_user),
            patch("handlers.start.insert_analytics_event", new_callable=AsyncMock),
        ):
            from handlers.start import cmd_start
            state_mock = AsyncMock()
            await cmd_start(message, state_mock)

        # Exactly one message — the consent screen — no welcome/menu hint sent
        assert message.answer.call_count == 1, (
            "Without consent, /start must send only the consent screen"
        )
        assert message.answer_photo.call_count == 0

        call = message.answer.call_args_list[0]
        assert "reply_markup" in call.kwargs, "Consent screen must carry the confirm button"
        text_arg = call.args[0] if call.args else call.kwargs.get("text", "")
        assert "персональных данных" in text_arg

    @pytest.mark.asyncio
    async def test_pdn_consent_callback_unlocks_welcome(self, new_user):
        """Confirming the ПДн-consent button records consent and immediately
        shows the normal welcome flow."""
        new_user.pdn_consent_at = None
        consented_user = _make_user_dataclass(
            telegram_id=888999000, pdn_consent_at=datetime.now()
        )

        callback = MagicMock()
        callback.from_user = MagicMock()
        callback.from_user.id = 888999000
        callback.data = "pdn:consent_start"
        callback.answer = AsyncMock()
        callback.message = MagicMock()
        callback.message.delete = AsyncMock()
        callback.message.answer = AsyncMock()
        callback.message.answer_photo = AsyncMock()

        with (
            patch("handlers.start.set_pdn_consent", new_callable=AsyncMock, return_value=consented_user),
            patch("handlers.start.insert_analytics_event", new_callable=AsyncMock),
        ):
            from handlers.start import cb_pdn_consent_start
            await cb_pdn_consent_start(callback)

        callback.answer.assert_called_once()
        callback.message.delete.assert_called_once()
        # Welcome flow ran on the callback's message (welcome/photo + menu hint)
        assert callback.message.answer.call_count >= 1

    # ------------------------------------------------------------------ #
    # 2. FAQ response — no Claude call                                     #
    # ------------------------------------------------------------------ #

    @pytest.mark.asyncio
    async def test_faq_response(self, new_user):
        """
        Sending an FAQ-matching message must return a canned answer without
        calling the Claude API and without incrementing chat_count.
        """
        original_count = new_user.chat_count  # 0

        message = _make_message(text="Сколько стоит консультация?")

        with (
            patch("handlers.chat.get_or_create_user", new_callable=AsyncMock, return_value=new_user),
            patch("handlers.chat.can_use_chat", return_value=True),
            patch("handlers.chat.ask_claude", new_callable=AsyncMock) as mock_claude,
            patch("handlers.chat.update_user", new_callable=AsyncMock) as mock_update,
            patch("handlers.chat.add_message_to_history", new_callable=AsyncMock),
            patch("handlers.chat.add_bonus_messages", new_callable=AsyncMock),
        ):
            from handlers.chat import handle_text_message
            await handle_text_message(message)

        # Claude must NOT be called for FAQ messages
        mock_claude.assert_not_called()

        # chat_count must NOT be incremented (update_user not called)
        mock_update.assert_not_called()
        assert new_user.chat_count == original_count, (
            "chat_count should not increment for FAQ responses"
        )

        # Bot must have answered
        message.answer.assert_called_once()
        answered_text = message.answer.call_args[0][0]
        # The FAQ answer for "стоимость / консультация" mentions price
        assert "2 000" in answered_text or "стоимость" in answered_text.lower() or "Консультация" in answered_text

    # ------------------------------------------------------------------ #
    # 3. Chat limit reached                                               #
    # ------------------------------------------------------------------ #

    @pytest.mark.asyncio
    async def test_chat_limit(self, limited_user):
        """
        When a non-subscribed user has chat_count >= FREE_CHAT_LIMIT and no bonus
        messages, the bot must send a subscription prompt instead of a Claude reply.
        """
        message = _make_message(text="Расскажи мне про газон")

        with (
            patch("handlers.chat.get_or_create_user", new_callable=AsyncMock, return_value=limited_user),
            patch("handlers.chat.can_use_chat", return_value=False),
            patch("handlers.chat.ask_claude", new_callable=AsyncMock) as mock_claude,
            patch("handlers.chat.subscribe_keyboard", return_value=MagicMock()),
        ):
            from handlers.chat import handle_text_message
            await handle_text_message(message)

        # Claude must NOT be called
        mock_claude.assert_not_called()

        # A subscription prompt must be sent
        message.answer.assert_called_once()
        prompt_text = message.answer.call_args[0][0]
        assert "Лимит" in prompt_text or "лимит" in prompt_text or "подписк" in prompt_text.lower(), (
            "Expected subscription prompt when limit is reached"
        )

    # ------------------------------------------------------------------ #
    # 4. Referral code generation                                          #
    # ------------------------------------------------------------------ #

    def test_referral_code(self):
        """
        _make_referral_code() must:
          - always start with "REF"
          - be deterministic (same id → same code)
          - handle id=0 gracefully
        """
        from services.database import _make_referral_code

        # Prefix check
        code = _make_referral_code(123456789)
        assert code.startswith("REF"), f"Expected REF prefix, got {code!r}"

        # Determinism
        assert _make_referral_code(123456789) == _make_referral_code(123456789)
        assert _make_referral_code(999999999) == _make_referral_code(999999999)

        # Different ids produce different codes
        assert _make_referral_code(1) != _make_referral_code(2)

        # Edge case: id = 0 → "REF0"
        code_zero = _make_referral_code(0)
        assert code_zero.startswith("REF")
        assert len(code_zero) >= 4

        # Max length constraint
        long_id_code = _make_referral_code(99999999999)
        assert long_id_code.startswith("REF")
        # "REF" (3) + up to 7 base-36 chars = 10 chars max
        assert len(long_id_code) <= 10, f"Code too long: {long_id_code!r}"

    # ------------------------------------------------------------------ #
    # 5. Promo code validation                                             #
    # ------------------------------------------------------------------ #

    @pytest.mark.asyncio
    async def test_promo_code_valid(self, mock_pool):
        """Valid active promo returns discount."""
        pool, conn = mock_pool

        future_expiry = datetime.now() + timedelta(days=30)
        conn.fetchrow = AsyncMock(return_value={
            "id": 1,
            "discount_pct": 20,
            "uses_left": 5,
            "expires_at": future_expiry,
        })
        conn.fetchval = AsyncMock(return_value=None)   # not used before
        conn.execute = AsyncMock()

        with patch("handlers.promo._pool", pool):
            from handlers.promo import apply_promo
            result = await apply_promo(telegram_id=111, code="SAVE20")

        assert result["ok"] is True
        assert result["discount"] == 20

    @pytest.mark.asyncio
    async def test_promo_code_expired(self, mock_pool):
        """Expired promo code is rejected."""
        pool, conn = mock_pool

        past_expiry = datetime.now() - timedelta(days=1)
        conn.fetchrow = AsyncMock(return_value={
            "id": 2,
            "discount_pct": 15,
            "uses_left": 3,
            "expires_at": past_expiry,
        })
        conn.fetchval = AsyncMock(return_value=None)
        conn.execute = AsyncMock()

        with patch("handlers.promo._pool", pool):
            from handlers.promo import apply_promo
            result = await apply_promo(telegram_id=222, code="OLD15")

        assert result["ok"] is False
        assert "истёк" in result["reason"].lower() or "expired" in result["reason"].lower()

    @pytest.mark.asyncio
    async def test_promo_code_inactive(self, mock_pool):
        """Promo with uses_left <= 0 is rejected."""
        pool, conn = mock_pool

        conn.fetchrow = AsyncMock(return_value={
            "id": 3,
            "discount_pct": 10,
            "uses_left": 0,
            "expires_at": None,
        })
        conn.fetchval = AsyncMock(return_value=None)
        conn.execute = AsyncMock()

        with patch("handlers.promo._pool", pool):
            from handlers.promo import apply_promo
            result = await apply_promo(telegram_id=333, code="USED10")

        assert result["ok"] is False
        assert "исчерп" in result["reason"].lower() or "uses" in result["reason"].lower()

    @pytest.mark.asyncio
    async def test_promo_code_not_found(self, mock_pool):
        """Unknown promo code returns not-found error."""
        pool, conn = mock_pool

        conn.fetchrow = AsyncMock(return_value=None)
        conn.fetchval = AsyncMock(return_value=None)
        conn.execute = AsyncMock()

        with patch("handlers.promo._pool", pool):
            from handlers.promo import apply_promo
            result = await apply_promo(telegram_id=444, code="GHOST")

        assert result["ok"] is False
        assert "найден" in result["reason"].lower() or "not found" in result["reason"].lower()


class TestBookingPhoneConsent:
    """152-ФЗ: перед вводом телефона в booking.py — отдельное подтверждение."""

    @pytest.mark.asyncio
    async def test_slot_pick_asks_phone_consent_not_phone(self, mock_pool):
        """Выбор слота ведёт на экран согласия на передачу телефона,
        а НЕ сразу в состояние ожидания номера."""
        pool, conn = mock_pool
        conn.fetchrow = AsyncMock(return_value={"slot_dt": datetime(2026, 9, 1, 10, 0)})

        callback = MagicMock()
        callback.data = "book_slot:7"
        callback.from_user = MagicMock(id=42)
        callback.answer = AsyncMock()
        callback.message = MagicMock()
        callback.message.edit_text = AsyncMock()

        state = AsyncMock()
        state.update_data = AsyncMock()
        state.set_state = AsyncMock()

        with patch("handlers.booking.get_pool", new_callable=AsyncMock, return_value=pool):
            from handlers.booking import cb_book_slot, BookingForm
            await cb_book_slot(callback, state)

        state.set_state.assert_called_once_with(BookingForm.waiting_phone_consent)
        text, kwargs = callback.message.edit_text.call_args.args, callback.message.edit_text.call_args.kwargs
        shown_text = text[0] if text else kwargs.get("text", "")
        assert "телефон" in shown_text.lower()
        assert "reply_markup" in kwargs
        buttons = kwargs["reply_markup"].inline_keyboard
        callback_datas = [b.callback_data for row in buttons for b in row]
        assert "book_phone_consent:accept" in callback_datas, (
            "Consent screen must offer the phone-consent confirm button"
        )

    @pytest.mark.asyncio
    async def test_phone_consent_accept_unlocks_contact_state(self):
        """После подтверждения — переход в waiting_contact, только тогда
        бот готов принять номер телефона."""
        callback = MagicMock()
        callback.answer = AsyncMock()
        callback.message = MagicMock()
        callback.message.edit_text = AsyncMock()

        state = AsyncMock()
        state.set_state = AsyncMock()

        from handlers.booking import cb_book_phone_consent, BookingForm
        await cb_book_phone_consent(callback, state)

        state.set_state.assert_called_once_with(BookingForm.waiting_contact)


# ---------------------------------------------------------------------------
# Standalone unit tests (no class needed but kept for grouping)
# ---------------------------------------------------------------------------

class TestCheckFaq:
    """Unit tests for the FAQ keyword matcher."""

    def test_price_keywords(self):
        from handlers.chat import check_faq
        assert check_faq("Сколько стоит консультация?") is not None
        assert check_faq("Какой у вас прайс?") is not None
        assert check_faq("Расценки на услуги") is not None

    def test_region_keywords(self):
        from handlers.chat import check_faq
        assert check_faq("Вы работаете в Нижнем Новгороде?") is not None

    def test_non_faq_message(self):
        from handlers.chat import check_faq
        assert check_faq("Какие цветы посадить под окном?") is None
        assert check_faq("Когда поливать газон?") is None

    def test_case_insensitive(self):
        from handlers.chat import check_faq
        assert check_faq("СКОЛЬКО СТОИТ") is not None
        assert check_faq("сколько стоит") is not None


class TestCanUseChat:
    """Unit tests for the chat usage gate."""

    def test_free_user_within_limit(self):
        from services.database import can_use_chat
        user = _make_user_dataclass(chat_count=5, is_subscribed=False)
        assert can_use_chat(user, limit=10) is True

    def test_free_user_at_limit(self):
        from services.database import can_use_chat
        user = _make_user_dataclass(chat_count=10, is_subscribed=False)
        assert can_use_chat(user, limit=10) is False

    def test_subscribed_user_ignores_limit(self):
        from services.database import can_use_chat
        user = _make_user_dataclass(chat_count=999, is_subscribed=True)
        assert can_use_chat(user, limit=10) is True
