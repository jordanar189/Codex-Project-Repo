"""SQLite persistence layer for the budgeting app.

Schema:
    categories(id, name UNIQUE, is_default, created_at)
    rules(id, merchant_pattern UNIQUE, category_id, created_at)
    transactions(id, txn_date, merchant, amount, category_id,
                 fiscal_year, fiscal_period, source_file,
                 imported_at, needs_review, raw_hash UNIQUE)
    settings(key PRIMARY KEY, value)

Amount convention: positive = income (inflow), negative = expense (outflow).
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterable, Iterator, Optional

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "budget.db"

DEFAULT_CATEGORIES = [
    "Housing",
    "Transportation",
    "Food",
    "Subscriptions",
    "Discretionary",
    "Miscellaneous",
]
INCOME_CATEGORY = "Income"
UNCATEGORIZED = "Uncategorized"

DEFAULT_SETTINGS = {
    "fiscal_year_start": "2024-01-07",
    "amount_sign_convention": "income_positive",
}


def _connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), detect_types=sqlite3.PARSE_DECLTYPES)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def get_conn(db_path: Path = DEFAULT_DB_PATH) -> Iterator[sqlite3.Connection]:
    conn = _connect(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(db_path: Path = DEFAULT_DB_PATH) -> None:
    """Create tables (if missing) and seed default categories + settings."""
    with get_conn(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                is_default INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                merchant_pattern TEXT NOT NULL UNIQUE,
                category_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                txn_date TEXT NOT NULL,
                merchant TEXT NOT NULL,
                amount REAL NOT NULL,
                category_id INTEGER,
                fiscal_year INTEGER,
                fiscal_period INTEGER,
                source_file TEXT,
                imported_at TEXT NOT NULL,
                needs_review INTEGER NOT NULL DEFAULT 1,
                raw_hash TEXT UNIQUE,
                FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE SET NULL
            );

            CREATE INDEX IF NOT EXISTS idx_txn_period
                ON transactions(fiscal_year, fiscal_period);
            CREATE INDEX IF NOT EXISTS idx_txn_review
                ON transactions(needs_review);

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            """
        )

        now = datetime.utcnow().isoformat(timespec="seconds")
        for name in DEFAULT_CATEGORIES + [INCOME_CATEGORY, UNCATEGORIZED]:
            conn.execute(
                "INSERT OR IGNORE INTO categories (name, is_default, created_at) "
                "VALUES (?, 1, ?)",
                (name, now),
            )

        for key, value in DEFAULT_SETTINGS.items():
            conn.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
                (key, value),
            )


# ---------- settings ----------

def get_setting(key: str, db_path: Path = DEFAULT_DB_PATH) -> Optional[str]:
    with get_conn(db_path) as conn:
        row = conn.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        ).fetchone()
        return row["value"] if row else None


def set_setting(key: str, value: str, db_path: Path = DEFAULT_DB_PATH) -> None:
    with get_conn(db_path) as conn:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )


# ---------- categories ----------

def list_categories(db_path: Path = DEFAULT_DB_PATH) -> list[sqlite3.Row]:
    with get_conn(db_path) as conn:
        return conn.execute(
            "SELECT id, name, is_default FROM categories ORDER BY name"
        ).fetchall()


def category_id_by_name(name: str, db_path: Path = DEFAULT_DB_PATH) -> Optional[int]:
    with get_conn(db_path) as conn:
        row = conn.execute(
            "SELECT id FROM categories WHERE name = ?", (name,)
        ).fetchone()
        return row["id"] if row else None


def add_category(name: str, db_path: Path = DEFAULT_DB_PATH) -> int:
    name = name.strip()
    if not name:
        raise ValueError("Category name cannot be empty")
    now = datetime.utcnow().isoformat(timespec="seconds")
    with get_conn(db_path) as conn:
        conn.execute(
            "INSERT OR IGNORE INTO categories (name, is_default, created_at) "
            "VALUES (?, 0, ?)",
            (name, now),
        )
        row = conn.execute(
            "SELECT id FROM categories WHERE name = ?", (name,)
        ).fetchone()
        return row["id"]


def rename_category(category_id: int, new_name: str, db_path: Path = DEFAULT_DB_PATH) -> None:
    new_name = new_name.strip()
    if not new_name:
        raise ValueError("Category name cannot be empty")
    with get_conn(db_path) as conn:
        conn.execute(
            "UPDATE categories SET name = ? WHERE id = ?", (new_name, category_id)
        )


def delete_category(category_id: int, db_path: Path = DEFAULT_DB_PATH) -> None:
    """Delete a non-default category. Transactions become uncategorized."""
    with get_conn(db_path) as conn:
        row = conn.execute(
            "SELECT is_default, name FROM categories WHERE id = ?", (category_id,)
        ).fetchone()
        if row is None:
            return
        if row["is_default"]:
            raise ValueError(f"Cannot delete default category '{row['name']}'")
        conn.execute("DELETE FROM categories WHERE id = ?", (category_id,))


# ---------- rules ----------

def list_rules(db_path: Path = DEFAULT_DB_PATH) -> list[sqlite3.Row]:
    with get_conn(db_path) as conn:
        return conn.execute(
            """
            SELECT r.id, r.merchant_pattern, r.category_id, c.name AS category_name
            FROM rules r
            JOIN categories c ON c.id = r.category_id
            ORDER BY r.merchant_pattern
            """
        ).fetchall()


def add_rule(pattern: str, category_id: int, db_path: Path = DEFAULT_DB_PATH) -> int:
    pattern = pattern.strip().lower()
    if not pattern:
        raise ValueError("Rule pattern cannot be empty")
    now = datetime.utcnow().isoformat(timespec="seconds")
    with get_conn(db_path) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO rules (merchant_pattern, category_id, created_at) "
            "VALUES (?, ?, ?)",
            (pattern, category_id, now),
        )
        row = conn.execute(
            "SELECT id FROM rules WHERE merchant_pattern = ?", (pattern,)
        ).fetchone()
        return row["id"]


def delete_rule(rule_id: int, db_path: Path = DEFAULT_DB_PATH) -> None:
    with get_conn(db_path) as conn:
        conn.execute("DELETE FROM rules WHERE id = ?", (rule_id,))


# ---------- transactions ----------

def insert_transactions(
    rows: Iterable[dict], db_path: Path = DEFAULT_DB_PATH
) -> tuple[int, int]:
    """Insert transactions, skipping duplicates by raw_hash.

    Returns (inserted_count, skipped_count).
    """
    inserted = 0
    skipped = 0
    now = datetime.utcnow().isoformat(timespec="seconds")
    with get_conn(db_path) as conn:
        for row in rows:
            try:
                conn.execute(
                    """
                    INSERT INTO transactions (
                        txn_date, merchant, amount, category_id,
                        fiscal_year, fiscal_period, source_file,
                        imported_at, needs_review, raw_hash
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        row["txn_date"],
                        row["merchant"],
                        float(row["amount"]),
                        row.get("category_id"),
                        row.get("fiscal_year"),
                        row.get("fiscal_period"),
                        row.get("source_file"),
                        now,
                        1 if row.get("needs_review", True) else 0,
                        row["raw_hash"],
                    ),
                )
                inserted += 1
            except sqlite3.IntegrityError:
                skipped += 1
    return inserted, skipped


def update_transaction_category(
    transaction_id: int,
    category_id: Optional[int],
    needs_review: bool = False,
    db_path: Path = DEFAULT_DB_PATH,
) -> None:
    with get_conn(db_path) as conn:
        conn.execute(
            "UPDATE transactions SET category_id = ?, needs_review = ? WHERE id = ?",
            (category_id, 1 if needs_review else 0, transaction_id),
        )


def fetch_transactions(
    fiscal_year: Optional[int] = None,
    fiscal_period: Optional[int] = None,
    needs_review: Optional[bool] = None,
    db_path: Path = DEFAULT_DB_PATH,
) -> list[sqlite3.Row]:
    sql = [
        "SELECT t.id, t.txn_date, t.merchant, t.amount, t.category_id, "
        "       t.fiscal_year, t.fiscal_period, t.source_file, t.needs_review, "
        "       COALESCE(c.name, ?) AS category_name "
        "FROM transactions t LEFT JOIN categories c ON c.id = t.category_id"
    ]
    params: list = [UNCATEGORIZED]
    where: list[str] = []
    if fiscal_year is not None:
        where.append("t.fiscal_year = ?")
        params.append(fiscal_year)
    if fiscal_period is not None:
        where.append("t.fiscal_period = ?")
        params.append(fiscal_period)
    if needs_review is not None:
        where.append("t.needs_review = ?")
        params.append(1 if needs_review else 0)
    if where:
        sql.append("WHERE " + " AND ".join(where))
    sql.append("ORDER BY t.txn_date DESC, t.id DESC")
    with get_conn(db_path) as conn:
        return conn.execute(" ".join(sql), params).fetchall()


def period_summary(
    fiscal_year: int, fiscal_period: int, db_path: Path = DEFAULT_DB_PATH
) -> dict:
    """Return income, expenses, net for the given fiscal period.

    Income = sum of positive amounts. Expenses = sum of |negative amounts|.
    """
    with get_conn(db_path) as conn:
        row = conn.execute(
            """
            SELECT
                COALESCE(SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END), 0) AS income,
                COALESCE(SUM(CASE WHEN amount < 0 THEN -amount ELSE 0 END), 0) AS expenses
            FROM transactions
            WHERE fiscal_year = ? AND fiscal_period = ?
            """,
            (fiscal_year, fiscal_period),
        ).fetchone()
    income = float(row["income"] or 0)
    expenses = float(row["expenses"] or 0)
    return {
        "fiscal_year": fiscal_year,
        "fiscal_period": fiscal_period,
        "income": income,
        "expenses": expenses,
        "net": income - expenses,
    }


def recent_period_summaries(
    limit: int = 5, db_path: Path = DEFAULT_DB_PATH
) -> list[dict]:
    """Return the most recent N (fiscal_year, fiscal_period) summaries with data."""
    with get_conn(db_path) as conn:
        rows = conn.execute(
            """
            SELECT fiscal_year, fiscal_period,
                COALESCE(SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END), 0) AS income,
                COALESCE(SUM(CASE WHEN amount < 0 THEN -amount ELSE 0 END), 0) AS expenses
            FROM transactions
            WHERE fiscal_year IS NOT NULL AND fiscal_period IS NOT NULL
            GROUP BY fiscal_year, fiscal_period
            ORDER BY fiscal_year DESC, fiscal_period DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [
        {
            "fiscal_year": r["fiscal_year"],
            "fiscal_period": r["fiscal_period"],
            "income": float(r["income"] or 0),
            "expenses": float(r["expenses"] or 0),
            "net": float(r["income"] or 0) - float(r["expenses"] or 0),
        }
        for r in rows
    ]
