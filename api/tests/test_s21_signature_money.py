"""Exact monetary verification, including real Bedrock currency-prefixed output."""
import pytest

from app.services.signed_sow import compute_diff


@pytest.mark.parametrize("approved,extracted,currency_a,currency_b,match", [
    ("USD 24000.00", "USD 24000.00", "USD", "USD", True),
    ("USD 24,000.00", "24000.00 USD", "USD", "USD", True),
    ("24000.00", "USD 24000", "USD", "USD", True),
    ("$24,000.00", "USD 24000", "USD", "USD", True),
    ("24000", "24000.00", None, None, True),
    ("USD 24000", "USD 24001", "USD", "USD", False),
    ("USD 24000", "CAD 24000", "USD", "CAD", False),
    ("24000", "24000", "USD", "INR", False),
    ("USD 24000", "USD 24000", "CAD", "USD", False),
    ("$24000", "$24000", None, None, False),
    ("USD 24000", "$24,000.00 USD", None, None, True),
    ("USD 24000", "$24000 CAD", None, None, False),
    ("USD 24000", "$24000 CAD", "USD", "USD", False),
    ("USD 24,00", "USD 2400", "USD", "USD", False),
    ("USD 24000 plus tax", "USD 24000 plus tax", "USD", "USD", False),
    ("NaN", "NaN", "USD", "USD", False),
    ("Infinity", "Infinity", "USD", "USD", False),
])
def test_signature_prices_preserve_amount_and_currency(approved, extracted, currency_a, currency_b, match):
    result = compute_diff({"price": {"value": approved}, "currency": {"value": currency_a}},
                          {"price": {"value": extracted}, "currency": {"value": currency_b}})
    price = next(row for row in result.fields if row["field"] == "price")
    assert price["match"] is match
