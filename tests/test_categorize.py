from budgeting.categorize import Rule, categorize


RULES = [
    Rule(pattern="starbucks", category_id=1, category_name="Food"),
    Rule(pattern="shell", category_id=2, category_name="Transportation"),
    Rule(pattern="shell oil 1234", category_id=3, category_name="Discretionary"),
]


def test_income_is_auto_assigned():
    result = categorize("ACME PAYROLL", 2500.0, RULES, income_category_id=99)
    assert result.category_id == 99
    assert result.needs_review is False


def test_substring_match_assigns_category():
    result = categorize("STARBUCKS #4521", -7.50, RULES)
    assert result.category_name == "Food"
    assert result.needs_review is False
    assert result.matched_pattern == "starbucks"


def test_longest_pattern_wins():
    result = categorize("SHELL OIL 1234 QUIK MART", -45.00, RULES)
    assert result.category_name == "Discretionary"
    assert result.matched_pattern == "shell oil 1234"


def test_no_match_flags_for_review():
    result = categorize("SOME WEIRD VENDOR", -12.34, RULES)
    assert result.category_id is None
    assert result.needs_review is True


def test_match_is_case_insensitive():
    result = categorize("starbucks reserve", -5.00, RULES)
    assert result.category_name == "Food"


def test_no_income_id_means_income_falls_through():
    result = categorize("ACME PAYROLL", 2500.0, RULES, income_category_id=None)
    # No rule matches "acme payroll" so it ends up flagged for review.
    assert result.needs_review is True
