from pathlib import Path

import pytest

from budgeting import db


@pytest.fixture
def tmp_db(tmp_path: Path) -> Path:
    path = tmp_path / "test.db"
    db.init_db(path)
    return path


def test_init_seeds_default_categories(tmp_db):
    names = [c["name"] for c in db.list_categories(tmp_db)]
    for expected in db.DEFAULT_CATEGORIES + ["Income", "Uncategorized"]:
        assert expected in names


def test_default_settings_present(tmp_db):
    assert db.get_setting("fiscal_year_start", tmp_db) == "2024-01-07"
    assert db.get_setting("amount_sign_convention", tmp_db) == "income_positive"


def test_insert_and_summary(tmp_db):
    food_id = db.category_id_by_name("Food", tmp_db)
    income_id = db.category_id_by_name("Income", tmp_db)

    rows = [
        {
            "txn_date": "2024-02-10",
            "merchant": "STARBUCKS",
            "amount": -5.0,
            "category_id": food_id,
            "fiscal_year": 2024,
            "fiscal_period": 2,
            "source_file": "test.csv",
            "needs_review": False,
            "raw_hash": "h1",
        },
        {
            "txn_date": "2024-02-15",
            "merchant": "PAYROLL",
            "amount": 1000.0,
            "category_id": income_id,
            "fiscal_year": 2024,
            "fiscal_period": 2,
            "source_file": "test.csv",
            "needs_review": False,
            "raw_hash": "h2",
        },
    ]
    inserted, skipped = db.insert_transactions(rows, tmp_db)
    assert inserted == 2 and skipped == 0

    # Re-inserting the same rows is a no-op via raw_hash uniqueness.
    inserted, skipped = db.insert_transactions(rows, tmp_db)
    assert inserted == 0 and skipped == 2

    summary = db.period_summary(2024, 2, tmp_db)
    assert summary["income"] == 1000.0
    assert summary["expenses"] == 5.0
    assert summary["net"] == 995.0


def test_recent_period_summaries(tmp_db):
    cat_id = db.category_id_by_name("Food", tmp_db)
    rows = [
        {
            "txn_date": "2024-02-10",
            "merchant": "M",
            "amount": -5.0,
            "category_id": cat_id,
            "fiscal_year": 2024,
            "fiscal_period": 2,
            "needs_review": False,
            "raw_hash": "a",
        },
        {
            "txn_date": "2024-03-10",
            "merchant": "M",
            "amount": -10.0,
            "category_id": cat_id,
            "fiscal_year": 2024,
            "fiscal_period": 3,
            "needs_review": False,
            "raw_hash": "b",
        },
    ]
    db.insert_transactions(rows, tmp_db)
    recent = db.recent_period_summaries(limit=5, db_path=tmp_db)
    assert len(recent) == 2
    assert recent[0]["fiscal_period"] == 3  # most recent first


def test_rules_round_trip(tmp_db):
    food_id = db.category_id_by_name("Food", tmp_db)
    rule_id = db.add_rule("starbucks", food_id, tmp_db)
    rules = db.list_rules(tmp_db)
    assert any(r["id"] == rule_id and r["category_name"] == "Food" for r in rules)
    db.delete_rule(rule_id, tmp_db)
    assert not db.list_rules(tmp_db)


def test_cannot_delete_default_category(tmp_db):
    food_id = db.category_id_by_name("Food", tmp_db)
    with pytest.raises(ValueError):
        db.delete_category(food_id, tmp_db)


def test_can_add_and_delete_custom_category(tmp_db):
    new_id = db.add_category("Travel", tmp_db)
    assert new_id is not None
    db.delete_category(new_id, tmp_db)
    assert db.category_id_by_name("Travel", tmp_db) is None
