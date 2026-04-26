# Budgeting App

A local-first Streamlit budgeting app with a 13-period fiscal calendar (each
period = 4 weeks), CSV import for bank transactions, rule-based merchant
categorization, and a SQLite store.

## Features

- **Dashboard** — current fiscal period income, expenses, and net profit, plus
  a table + chart of the last five fiscal periods and a category breakdown.
- **Data Management** — upload bank CSVs, preview parsed rows, import with
  automatic rule-based categorization, and quickly assign categories to
  flagged transactions via dropdown. Optionally save the assignment as a
  reusable rule.
- **Settings** — manage the fiscal-year anchor date, default amount sign
  convention, expense categories, and merchant categorization rules.

Default categories: **Housing, Transportation, Food, Subscriptions,
Discretionary, Miscellaneous** (plus an auto-managed *Income* category).

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

The SQLite database is stored at `data/budget.db` (auto-created, gitignored).

## CSV format

The parser is column-name driven and case-insensitive. It needs:

- A **date** column: `date`, `transaction date`, `posted date`, …
- A **merchant** column: `description`, `merchant`, `payee`, …
- An **amount** column: either a single signed `amount` column, or split
  `debit` / `credit` columns.

Pick the right sign convention at upload time:

- *Positive = income (deposit)* — typical of accounting exports.
- *Positive = expense (debit)* — typical of credit-card statements.

Internally the app stores amounts as *positive = income, negative = expense*.

## Fiscal calendar

A fiscal year is 13 periods × 28 days = 364 days. The anchor date in
**Settings → Fiscal calendar** marks the start of period 1; all transaction
periods are computed from that anchor.

## Categorization

Each rule is a (lowercase) substring of the merchant string mapped to a
category. The longest matching pattern wins, so you can layer broad and
specific rules. Income transactions (amount > 0) are auto-assigned to the
*Income* category and never flagged for review. Anything else without a rule
match is flagged for manual categorization.

## Deploying to Streamlit Cloud

1. Push this branch to GitHub.
2. On [share.streamlit.io](https://share.streamlit.io), pick the repo,
   branch (`budgeting-app`), and main file (`app.py`).
3. Streamlit Cloud installs `requirements.txt` automatically.

> Note: Streamlit Cloud's filesystem is ephemeral. SQLite data persists for
> the lifetime of the container but is wiped on redeploy. For durable cloud
> storage, mount a volume or swap `budgeting/db.py` for a hosted DB.

## Tests

```bash
python -m pytest tests
```
