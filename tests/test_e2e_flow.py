"""
tests/test_e2e_flow.py
End-to-end integration-style tests for the VashSad Telegram bot.

Verifies complete user journeys using mocked Telegram API and Claude API.
Uses pytest + pytest-asyncio + unittest.mock.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Any, Optional
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
        username: Optional[str] = "testuser"
        first_name: Optional[str] = "Test"
        region: Optional[str] = None
        is_subscribed: bool = False
        chat_count: int = 0
        photo_count: int = 0
        plants_count: int = 0
        plot_size: Optional[float] = None
        chat_history: list = field(default_factory=list)
        created_at: datetime = field(default_factory=datetime.now)
        subscription_expires_at: Optional[datetime] = None
        referral_code: Optional[str] = None
        referred_by: Optional[int] = None
        bonus_messages: int = 0
        lang: str = "ru"

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
    date: Optional[datetime] = None,
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
            patch("handlers.start.t", side_effect=lambda key, lang: "{bot_name} {designer_name}" if key == "welcome" else "Hint"),
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
