"""Data Management — upload CSVs, review imports, manually categorize."""

from __future__ import annotations

import io
from datetime import date

import pandas as pd
import streamlit as st

from budgeting import categorize as cat
from budgeting import db, fiscal, ingest

st.set_page_config(page_title="Data Management", page_icon="📥", layout="wide")
db.init_db()

st.title("📥 Data Management")

fy_start = db.get_setting("fiscal_year_start") or "2024-01-07"
sign_default = db.get_setting("amount_sign_convention") or "income_positive"


def _build_rules() -> list[cat.Rule]:
    return [
        cat.Rule(
            pattern=r["merchant_pattern"],
            category_id=r["category_id"],
            category_name=r["category_name"],
        )
        for r in db.list_rules()
    ]


def _income_id() -> int | None:
    return db.category_id_by_name("Income")


# ---------------- Upload tab ----------------

upload_tab, review_tab, browse_tab = st.tabs(
    ["Upload CSV", "Review uncategorized", "Browse all transactions"]
)

with upload_tab:
    st.subheader("Upload a bank CSV")
    st.caption(
        "Expected columns (case-insensitive): a date column "
        "(`date`, `posted date`, …), a merchant column "
        "(`description`, `merchant`, `payee`, …), and either a signed `amount` "
        "column or split `debit` / `credit` columns."
    )

    sign_choice = st.radio(
        "Amount sign convention in your CSV",
        options=["income_positive", "expenses_positive"],
        index=0 if sign_default == "income_positive" else 1,
        format_func=lambda x: (
            "Positive = income (deposit)"
            if x == "income_positive"
            else "Positive = expense (debit)"
        ),
        horizontal=True,
    )

    uploaded = st.file_uploader("CSV file", type=["csv"])
    if uploaded is not None:
        try:
            parsed, warnings = ingest.parse_csv(
                io.BytesIO(uploaded.getvalue()),
                sign_convention=sign_choice,
                source_file=uploaded.name,
            )
        except Exception as exc:
            st.error(f"Could not parse CSV: {exc}")
            parsed, warnings = [], []

        for w in warnings:
            st.warning(w)

        if parsed:
            preview_df = pd.DataFrame(
                [
                    {
                        "Date": p.txn_date.isoformat(),
                        "Merchant": p.merchant,
                        "Amount": p.amount,
                    }
                    for p in parsed
                ]
            )
            st.write(f"Parsed **{len(parsed)}** transactions from `{uploaded.name}`.")
            st.dataframe(
                preview_df,
                hide_index=True,
                use_container_width=True,
                column_config={
                    "Amount": st.column_config.NumberColumn(format="$%.2f"),
                },
            )

            if st.button("Import these transactions", type="primary"):
                rules = _build_rules()
                income_id = _income_id()
                rows = []
                for p in parsed:
                    period = fiscal.period_for_date(p.txn_date, fy_start)
                    result = cat.categorize(
                        merchant=p.merchant,
                        amount=p.amount,
                        rules=rules,
                        income_category_id=income_id,
                    )
                    rows.append(
                        {
                            "txn_date": p.txn_date.isoformat(),
                            "merchant": p.merchant,
                            "amount": p.amount,
                            "category_id": result.category_id,
                            "fiscal_year": period.fiscal_year,
                            "fiscal_period": period.fiscal_period,
                            "source_file": uploaded.name,
                            "needs_review": result.needs_review,
                            "raw_hash": p.raw_hash,
                        }
                    )

                inserted, skipped = db.insert_transactions(rows)
                auto_count = sum(1 for r in rows if not r["needs_review"])
                review_count = sum(1 for r in rows if r["needs_review"])
                st.success(
                    f"Imported {inserted} new transaction(s); "
                    f"{skipped} duplicate(s) skipped. "
                    f"Auto-categorized: {auto_count}, flagged for review: "
                    f"{review_count}."
                )

# ---------------- Review tab ----------------

with review_tab:
    st.subheader("Review uncategorized transactions")
    pending = db.fetch_transactions(needs_review=True)
    if not pending:
        st.success("Nothing to review — every transaction has a category. 🎉")
    else:
        st.caption(
            f"{len(pending)} transaction(s) need a category. "
            "Pick one from the dropdown, then click **Save category**. "
            "Tick *Create a rule* to auto-categorize this merchant in the future."
        )
        cats = db.list_categories()
        cat_options = {c["name"]: c["id"] for c in cats if c["name"] != "Uncategorized"}
        cat_names = list(cat_options.keys())

        for txn in pending:
            with st.container(border=True):
                top = st.columns([2, 3, 1, 2, 2])
                top[0].write(txn["txn_date"])
                top[1].write(f"**{txn['merchant']}**")
                top[2].write(f"${txn['amount']:,.2f}")
                top[3].write(
                    f"FY{txn['fiscal_year']} P{int(txn['fiscal_period']):02d}"
                    if txn["fiscal_year"]
                    else "—"
                )
                top[4].caption(txn["source_file"] or "")

                with st.form(key=f"form_txn_{txn['id']}", clear_on_submit=False):
                    c1, c2, c3 = st.columns([2, 2, 1])
                    chosen = c1.selectbox(
                        "Category",
                        options=cat_names,
                        key=f"cat_{txn['id']}",
                        label_visibility="collapsed",
                    )
                    pattern_default = txn["merchant"].lower()[:30]
                    pattern = c2.text_input(
                        "Rule pattern (substring of merchant)",
                        value=pattern_default,
                        key=f"pat_{txn['id']}",
                        label_visibility="collapsed",
                    )
                    create_rule = c2.checkbox(
                        "Create a rule for this merchant",
                        key=f"rule_{txn['id']}",
                    )
                    submitted = c3.form_submit_button("Save category", type="primary")

                    if submitted:
                        category_id = cat_options[chosen]
                        db.update_transaction_category(
                            txn["id"], category_id, needs_review=False
                        )
                        if create_rule and pattern.strip():
                            db.add_rule(pattern.strip(), category_id)
                        st.rerun()

# ---------------- Browse tab ----------------

with browse_tab:
    st.subheader("All transactions")
    all_txns = db.fetch_transactions()
    if not all_txns:
        st.info("No transactions stored yet.")
    else:
        df = pd.DataFrame(
            [
                {
                    "Date": t["txn_date"],
                    "Merchant": t["merchant"],
                    "Amount": t["amount"],
                    "Category": t["category_name"],
                    "FY": t["fiscal_year"],
                    "Period": t["fiscal_period"],
                    "Needs Review": bool(t["needs_review"]),
                    "Source": t["source_file"],
                }
                for t in all_txns
            ]
        )
        st.dataframe(
            df,
            hide_index=True,
            use_container_width=True,
            column_config={
                "Amount": st.column_config.NumberColumn(format="$%.2f"),
            },
        )
