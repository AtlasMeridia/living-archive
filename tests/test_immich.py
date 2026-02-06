"""Tests for immich.py: date_estimate_to_iso edge cases."""

from src.immich import date_estimate_to_iso


class TestDateEstimateToIso:
    def test_year_only(self):
        assert date_estimate_to_iso("1978") == "1978-01-01T00:00:00.000Z"

    def test_year_month(self):
        assert date_estimate_to_iso("1978-06") == "1978-06-01T00:00:00.000Z"

    def test_full_date(self):
        assert date_estimate_to_iso("1978-06-15") == "1978-06-15T00:00:00.000Z"

    def test_year_month_day_format(self):
        """Ensure the output always ends with T00:00:00.000Z."""
        result = date_estimate_to_iso("2023-12-25")
        assert result.endswith("T00:00:00.000Z")

    def test_single_digit_month(self):
        """Months like '3' should pass through as-is (no zero-padding added)."""
        result = date_estimate_to_iso("1978-3")
        assert result == "1978-3-01T00:00:00.000Z"
