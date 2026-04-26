import io
from datetime import date

import pytest

from budgeting import ingest


SIGNED_CSV = """Date,Description,Amount
2024-02-10,STARBUCKS #421,-5.00
2024-02-15,ACME PAYROLL,2500.00
2024-02-16,"AMZN Mktp US*1A2B3",-19.99
"""

DEBIT_CREDIT_CSV = """Posted Date,Payee,Debit,Credit
02/10/2024,STARBUCKS,5.00,
02/15/2024,PAYROLL,,2500.00
"""

EXPENSES_POSITIVE_CSV = """Date,Merchant,Amount
2024-02-10,STARBUCKS,5.00
2024-02-15,REFUND,-12.50
"""


def test_parse_signed_amount_csv():
    parsed, warnings = ingest.parse_csv(io.StringIO(SIGNED_CSV))
    assert warnings == []
    assert len(parsed) == 3
    assert parsed[0].txn_date == date(2024, 2, 10)
    assert parsed[0].amount == -5.0
    assert parsed[1].amount == 2500.0


def test_parse_debit_credit_csv():
    parsed, _ = ingest.parse_csv(io.StringIO(DEBIT_CREDIT_CSV))
    amounts = sorted(p.amount for p in parsed)
    assert amounts == [-5.0, 2500.0]


def test_expenses_positive_flips_sign():
    parsed, _ = ingest.parse_csv(
        io.StringIO(EXPENSES_POSITIVE_CSV),
        sign_convention="expenses_positive",
    )
    by_merchant = {p.merchant: p.amount for p in parsed}
    assert by_merchant["STARBUCKS"] == -5.0
    assert by_merchant["REFUND"] == 12.5


def test_missing_required_column_raises():
    bad = "Foo,Bar\n1,2\n"
    with pytest.raises(ValueError):
        ingest.parse_csv(io.StringIO(bad))


def test_zero_amount_is_skipped_with_warning():
    csv = "Date,Description,Amount\n2024-02-10,VOID,0.00\n"
    parsed, warnings = ingest.parse_csv(io.StringIO(csv))
    assert parsed == []
    assert any("zero amount" in w for w in warnings)


def test_raw_hash_is_deterministic():
    parsed1, _ = ingest.parse_csv(io.StringIO(SIGNED_CSV))
    parsed2, _ = ingest.parse_csv(io.StringIO(SIGNED_CSV))
    assert [p.raw_hash for p in parsed1] == [p.raw_hash for p in parsed2]
