"""
pytest test suite for ВашСад bot handlers.
Run: pytest tests/test_handlers.py -v

Tests pure/synchronous functions only — no DB or Telegram connection needed.
"""
import sys
import os

import pytest

# Make sure project root is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# 1. FAQ matching — handlers/chat.py :: check_faq
# ---------------------------------------------------------------------------

class TestCheckFaq:
    """Tests for the check_faq() function in handlers/chat.py."""

    @pytest.fixture(autouse=True)
    def _import(self):
        # Import lazily so that missing aiogram doesn't break collection
        try:
            from handlers.chat import check_faq, FAQ_PATTERNS
            self.check_faq = check_faq
            self.FAQ_PATTERNS = FAQ_PATTERNS
        except ImportError as exc:
            pytest.skip(f"Could not import handlers.chat: {exc}")

    def test_price_keyword_returns_nonempty(self):
        result = self.check_faq("цена")
        assert result is not None
        assert len(result) > 0

    def test_price_keyword_stoimost(self):
        result = self.check_faq("сколько стоит консультация?")
        assert result is not None and len(result) > 0

    def test_booking_keyword_returns_nonempty(self):
        result = self.check_faq("как записаться")
        assert result is not None
        assert len(result) > 0

    def test_booking_keyword_consult(self):
        # FAQ_PATTERNS matches keyword "консультация" (nominative) exactly as substring
        result = self.check_faq("нужна консультация дизайнера")
        assert result is not None and len(result) > 0

    def test_unknown_query_returns_none(self):
        result = self.check_faq("xyzznotafaq")
        # check_faq returns None for unmatched text
        assert not result  # None or empty string both acceptable

    def test_unknown_gibberish_returns_none(self):
        result = self.check_faq("абвгдабвгд12345")
        assert not result

    def test_region_keyword_match(self):
        result = self.check_faq("где вы работаете, нижний новгород?")
        assert result is not None and len(result) > 0

    def test_guarantee_keyword_match(self):
        result = self.check_faq("есть ли гарантия на работы?")
        assert result is not None and len(result) > 0

    def test_faq_answer_is_string(self):
        result = self.check_faq("прайс")
        assert isinstance(result, str)

    def test_case_insensitive_match(self):
        lower = self.check_faq("цена")
        upper = self.check_faq("ЦЕНА")
        assert lower == upper

    def test_faq_patterns_nonempty(self):
        assert len(self.FAQ_PATTERNS) > 0

    def test_each_pattern_has_keywords_and_answer(self):
        for pattern in self.FAQ_PATTERNS:
            assert "keywords" in pattern
            assert "answer" in pattern
            assert len(pattern["keywords"]) > 0
            assert len(pattern["answer"]) > 0


# ---------------------------------------------------------------------------
# 2. Referral code generation — services/database.py :: _make_referral_code
# ---------------------------------------------------------------------------

class TestReferralCode:
    """Tests for _make_referral_code() in services/database.py."""

    @pytest.fixture(autouse=True)
    def _import(self):
        try:
            from services.database import _make_referral_code
            self.make_code = _make_referral_code
        except ImportError as exc:
            pytest.skip(f"Could not import services.database: {exc}")

    def test_returns_string(self):
        code = self.make_code(123456789)
        assert isinstance(code, str)

    def test_has_ref_prefix(self):
        code = self.make_code(123456789)
        assert code.startswith("REF")

    def test_deterministic_same_input(self):
        code1 = self.make_code(123456789)
        code2 = self.make_code(123456789)
        assert code1 == code2

    def test_different_ids_different_codes(self):
        code_a = self.make_code(111111111)
        code_b = self.make_code(222222222)
        assert code_a != code_b

    def test_max_length(self):
        # "REF" (3) + up to 7 base-36 chars = max 10 chars
        code = self.make_code(123456789)
        assert len(code) <= 10

    def test_min_length(self):
        # At minimum "REF" + "0" = 4 chars
        code = self.make_code(0)
        assert len(code) >= 4

    def test_uppercase_only(self):
        code = self.make_code(987654321)
        assert code == code.upper()

    def test_alphanumeric_after_prefix(self):
        code = self.make_code(123456789)
        suffix = code[3:]
        assert suffix.isalnum()

    def test_large_id(self):
        code = self.make_code(9_999_999_999)
        assert code.startswith("REF")
        assert len(code) <= 10


# ---------------------------------------------------------------------------
# 3. Price constants — config.py :: SERVICES and SUBSCRIPTION_PRICE
# ---------------------------------------------------------------------------

class TestPriceConstants:
    """Tests for price-related constants in config.py."""

    @pytest.fixture(autouse=True)
    def _import(self):
        try:
            import config
            self.config = config
        except ImportError as exc:
            pytest.skip(f"Could not import config: {exc}")

    def test_subscription_price_is_positive(self):
        assert self.config.SUBSCRIPTION_PRICE > 0

    def test_subscription_price_is_int(self):
        assert isinstance(self.config.SUBSCRIPTION_PRICE, int)

    def test_services_dict_exists(self):
        assert hasattr(self.config, "SERVICES")
        assert isinstance(self.config.SERVICES, dict)

    def test_services_not_empty(self):
        assert len(self.config.SERVICES) > 0

    def test_each_service_has_required_keys(self):
        required = {"name", "price", "duration", "description"}
        for key, svc in self.config.SERVICES.items():
            missing = required - svc.keys()
            assert not missing, f"Service '{key}' missing keys: {missing}"

    def test_consult_price_positive(self):
        svc = self.config.SERVICES.get("consult")
        assert svc is not None
        assert svc["price"] > 0

    def test_concept_price_greater_than_consult(self):
        consult = self.config.SERVICES["consult"]["price"]
        concept = self.config.SERVICES["concept"]["price"]
        assert concept > consult

    def test_free_limits_are_positive(self):
        assert self.config.FREE_CHAT_LIMIT > 0
        assert self.config.FREE_PHOTO_LIMIT > 0
        assert self.config.FREE_PLANTS_LIMIT > 0


# ---------------------------------------------------------------------------
# 4. Helper utilities in handlers/order.py
# ---------------------------------------------------------------------------

class TestOrderHelpers:
    """Tests for pure helper functions in handlers/order.py."""

    @pytest.fixture(autouse=True)
    def _import(self):
        try:
            from handlers.order import normalize_phone, is_foreign_email
            self.normalize_phone = normalize_phone
            self.is_foreign_email = is_foreign_email
        except ImportError as exc:
            pytest.skip(f"Could not import handlers.order: {exc}")

    def test_normalize_phone_11_digits_starting_8(self):
        assert self.normalize_phone("89161234567") == "+79161234567"

    def test_normalize_phone_11_digits_starting_7(self):
        assert self.normalize_phone("79161234567") == "+79161234567"

    def test_normalize_phone_10_digits_starting_9(self):
        assert self.normalize_phone("9161234567") == "+79161234567"

    def test_normalize_phone_already_formatted(self):
        result = self.normalize_phone("+79161234567")
        assert result.startswith("+")

    def test_normalize_phone_strips_dashes(self):
        # digits extracted regardless of separators
        result = self.normalize_phone("8-916-123-45-67")
        assert result == "+79161234567"

    def test_is_foreign_email_gmail(self):
        assert self.is_foreign_email("user@gmail.com") is True

    def test_is_foreign_email_yahoo(self):
        assert self.is_foreign_email("user@yahoo.com") is True

    def test_is_foreign_email_yandex_allowed(self):
        assert self.is_foreign_email("user@yandex.ru") is False

    def test_is_foreign_email_mailru_allowed(self):
        assert self.is_foreign_email("user@mail.ru") is False

    def test_is_foreign_email_no_at_sign(self):
        assert self.is_foreign_email("notanemail") is False

    def test_is_foreign_email_icloud(self):
        assert self.is_foreign_email("user@icloud.com") is True
