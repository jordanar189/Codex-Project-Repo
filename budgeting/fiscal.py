"""Thirteen-period fiscal calendar.

Each fiscal year contains 13 periods of exactly 4 weeks (28 days). The full
year is therefore 364 days; users can re-anchor the year start to keep it
aligned with the calendar.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Optional

PERIODS_PER_YEAR = 13
DAYS_PER_PERIOD = 28
DAYS_PER_FISCAL_YEAR = PERIODS_PER_YEAR * DAYS_PER_PERIOD  # 364


@dataclass(frozen=True)
class FiscalPeriod:
    fiscal_year: int
    fiscal_period: int  # 1..13
    start_date: date
    end_date: date  # inclusive

    @property
    def label(self) -> str:
        return f"FY{self.fiscal_year} P{self.fiscal_period:02d}"

    @property
    def date_range_label(self) -> str:
        return f"{self.start_date.isoformat()} → {self.end_date.isoformat()}"


def _parse_date(value: date | str) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    return datetime.strptime(value, "%Y-%m-%d").date()


def period_for_date(
    txn_date: date | str, fiscal_year_start: date | str
) -> FiscalPeriod:
    """Return the fiscal period that contains txn_date.

    The fiscal year number equals the calendar year of the period's start date.
    """
    txn = _parse_date(txn_date)
    anchor = _parse_date(fiscal_year_start)

    delta_days = (txn - anchor).days
    year_offset, day_in_year = divmod(delta_days, DAYS_PER_FISCAL_YEAR)
    if day_in_year < 0:  # for negative delta_days
        year_offset -= 1
        day_in_year += DAYS_PER_FISCAL_YEAR

    period_index = day_in_year // DAYS_PER_PERIOD  # 0..12
    period_start = anchor + timedelta(
        days=year_offset * DAYS_PER_FISCAL_YEAR + period_index * DAYS_PER_PERIOD
    )
    period_end = period_start + timedelta(days=DAYS_PER_PERIOD - 1)
    fiscal_year = period_start.year

    return FiscalPeriod(
        fiscal_year=fiscal_year,
        fiscal_period=period_index + 1,
        start_date=period_start,
        end_date=period_end,
    )


def current_period(
    fiscal_year_start: date | str, today: Optional[date] = None
) -> FiscalPeriod:
    return period_for_date(today or date.today(), fiscal_year_start)


def period_bounds(
    fiscal_year: int, fiscal_period: int, fiscal_year_start: date | str
) -> tuple[date, date]:
    """Return (start, end) for a (fiscal_year, fiscal_period) tuple.

    Searches backward/forward from the anchor to find the period whose start
    falls in the target fiscal_year.
    """
    if not 1 <= fiscal_period <= PERIODS_PER_YEAR:
        raise ValueError("fiscal_period must be between 1 and 13")
    anchor = _parse_date(fiscal_year_start)
    # Estimate offset using anchor year vs target year.
    year_offset = fiscal_year - anchor.year
    # Walk +/- a few cycles to land on the period whose start.year == fiscal_year.
    for delta in range(-2, 3):
        candidate_offset = year_offset + delta
        start = anchor + timedelta(
            days=candidate_offset * DAYS_PER_FISCAL_YEAR
            + (fiscal_period - 1) * DAYS_PER_PERIOD
        )
        if start.year == fiscal_year:
            return start, start + timedelta(days=DAYS_PER_PERIOD - 1)
    raise ValueError(
        f"Could not locate FY{fiscal_year} P{fiscal_period} from anchor {anchor}"
    )
