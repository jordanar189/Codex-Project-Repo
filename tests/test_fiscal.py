from datetime import date

from budgeting import fiscal


ANCHOR = date(2024, 1, 7)  # a Sunday


def test_period_at_anchor_is_p1():
    p = fiscal.period_for_date(ANCHOR, ANCHOR)
    assert p.fiscal_year == 2024
    assert p.fiscal_period == 1
    assert p.start_date == ANCHOR
    assert (p.end_date - p.start_date).days == 27


def test_period_two_is_28_days_later():
    p = fiscal.period_for_date(date(2024, 2, 4), ANCHOR)
    assert p.fiscal_period == 2
    assert p.fiscal_year == 2024


def test_period_thirteen_is_last_period():
    # P13 starts 12 * 28 = 336 days after anchor.
    p = fiscal.period_for_date(date(2024, 12, 8), ANCHOR)
    assert p.fiscal_period == 13


def test_next_year_starts_after_364_days():
    p = fiscal.period_for_date(date(2025, 1, 5), ANCHOR)
    assert p.fiscal_year == 2025
    assert p.fiscal_period == 1


def test_date_before_anchor_lands_in_previous_year():
    p = fiscal.period_for_date(date(2024, 1, 6), ANCHOR)
    assert p.fiscal_year == 2023
    assert p.fiscal_period == 13


def test_period_bounds_round_trips():
    p = fiscal.period_for_date(date(2024, 6, 1), ANCHOR)
    start, end = fiscal.period_bounds(p.fiscal_year, p.fiscal_period, ANCHOR)
    assert start == p.start_date
    assert end == p.end_date


def test_label_format():
    p = fiscal.period_for_date(date(2024, 1, 7), ANCHOR)
    assert p.label == "FY2024 P01"
