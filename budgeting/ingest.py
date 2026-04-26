"""CSV ingestion for bank transactions.

The parser is column-name driven and tolerant of common bank export formats.
It accepts either a single signed `amount` column or split debit/credit columns.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date, datetime
from typing import Iterable, Optional

import pandas as pd

DATE_CANDIDATES = [
    "date", "transaction date", "txn date", "posted date", "post date", "posting date",
]
MERCHANT_CANDIDATES = [
    "merchant", "description", "name", "payee", "details", "memo",
]
AMOUNT_CANDIDATES = ["amount", "transaction amount"]
DEBIT_CANDIDATES = ["debit", "withdrawal", "withdrawals", "outflow"]
CREDIT_CANDIDATES = ["credit", "deposit", "deposits", "inflow"]


@dataclass
class ParsedTxn:
    txn_date: date
    merchant: str
    amount: float
    raw_hash: str


def _find_column(df: pd.DataFrame, candidates: list[str]) -> Optional[str]:
    lookup = {c.lower().strip(): c for c in df.columns}
    for cand in candidates:
        if cand in lookup:
            return lookup[cand]
    return None


def _parse_date_value(value) -> Optional[date]:
    if pd.isna(value):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    try:
        return pd.to_datetime(text).date()
    except (ValueError, TypeError):
        return None


def _to_float(value) -> Optional[float]:
    if pd.isna(value):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", "").replace("$", "")
    if not text:
        return None
    if text.startswith("(") and text.endswith(")"):
        text = "-" + text[1:-1]
    try:
        return float(text)
    except ValueError:
        return None


def parse_csv(
    file_or_path,
    sign_convention: str = "income_positive",
    source_file: Optional[str] = None,
) -> tuple[list[ParsedTxn], list[str]]:
    """Parse a bank CSV file-like object or path.

    sign_convention:
        - "income_positive": positive amount = income (deposit). Stored as-is.
        - "expenses_positive": positive amount = expense (debit). Sign is flipped
          so internal storage stays positive=income.

    Returns (transactions, warnings).
    """
    warnings: list[str] = []
    df = pd.read_csv(file_or_path)
    if df.empty:
        return [], ["CSV is empty."]

    date_col = _find_column(df, DATE_CANDIDATES)
    merchant_col = _find_column(df, MERCHANT_CANDIDATES)
    amount_col = _find_column(df, AMOUNT_CANDIDATES)
    debit_col = _find_column(df, DEBIT_CANDIDATES)
    credit_col = _find_column(df, CREDIT_CANDIDATES)

    if date_col is None:
        raise ValueError(
            f"Could not find a date column. Expected one of: {DATE_CANDIDATES}"
        )
    if merchant_col is None:
        raise ValueError(
            f"Could not find a merchant/description column. "
            f"Expected one of: {MERCHANT_CANDIDATES}"
        )
    if amount_col is None and not (debit_col or credit_col):
        raise ValueError(
            "Could not find an amount column or debit/credit columns."
        )

    parsed: list[ParsedTxn] = []
    for idx, row in df.iterrows():
        txn_date = _parse_date_value(row[date_col])
        if txn_date is None:
            warnings.append(f"Row {idx + 2}: unparseable date, skipping.")
            continue

        merchant_raw = row[merchant_col]
        merchant = "" if pd.isna(merchant_raw) else str(merchant_raw).strip()
        if not merchant:
            warnings.append(f"Row {idx + 2}: missing merchant, skipping.")
            continue

        if amount_col is not None:
            amount = _to_float(row[amount_col])
            if amount is None:
                warnings.append(f"Row {idx + 2}: unparseable amount, skipping.")
                continue
            if sign_convention == "expenses_positive":
                amount = -amount
        else:
            debit = _to_float(row[debit_col]) if debit_col else None
            credit = _to_float(row[credit_col]) if credit_col else None
            if debit is None and credit is None:
                warnings.append(f"Row {idx + 2}: no debit/credit value, skipping.")
                continue
            amount = (credit or 0.0) - (debit or 0.0)

        if amount == 0:
            warnings.append(f"Row {idx + 2}: zero amount, skipping.")
            continue

        raw_key = f"{txn_date.isoformat()}|{merchant.lower()}|{amount:.4f}"
        raw_hash = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

        parsed.append(
            ParsedTxn(
                txn_date=txn_date,
                merchant=merchant,
                amount=amount,
                raw_hash=raw_hash,
            )
        )

    return parsed, warnings
