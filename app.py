"""Streamlit budgeting app — Dashboard (entry point).

Run locally with: streamlit run app.py
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from budgeting import db, fiscal

st.set_page_config(page_title="Budget Dashboard", page_icon="💰", layout="wide")

db.init_db()

st.title("💰 Budget Dashboard")

fy_start = db.get_setting("fiscal_year_start") or "2024-01-07"
try:
    current = fiscal.current_period(fy_start)
except Exception as exc:  # pragma: no cover
    st.error(f"Could not compute fiscal period: {exc}")
    st.stop()

st.caption(
    f"Current period: **{current.label}**  "
    f"({current.date_range_label})  ·  Today: {date.today().isoformat()}"
)

summary = db.period_summary(current.fiscal_year, current.fiscal_period)

col1, col2, col3 = st.columns(3)
col1.metric("Income", f"${summary['income']:,.2f}")
col2.metric("Total Expenses", f"${summary['expenses']:,.2f}")
col3.metric(
    "Net Profit",
    f"${summary['net']:,.2f}",
    delta=f"{summary['net']:,.2f}",
    delta_color="normal",
)

uncat = db.fetch_transactions(
    fiscal_year=current.fiscal_year,
    fiscal_period=current.fiscal_period,
    needs_review=True,
)
if uncat:
    st.warning(
        f"{len(uncat)} transaction(s) in this period need review. "
        "Open **Data Management** to categorize them."
    )

st.divider()
st.subheader("Last 5 fiscal periods")

recent = db.recent_period_summaries(limit=5)
if not recent:
    st.info("No transactions yet. Go to **Data Management** to upload a CSV.")
else:
    df = pd.DataFrame(recent)
    df["Period"] = df.apply(
        lambda r: f"FY{int(r['fiscal_year'])} P{int(r['fiscal_period']):02d}", axis=1
    )
    df = df[["Period", "income", "expenses", "net"]].rename(
        columns={"income": "Income", "expenses": "Expenses", "net": "Net"}
    )
    st.dataframe(
        df,
        hide_index=True,
        use_container_width=True,
        column_config={
            "Income": st.column_config.NumberColumn(format="$%.2f"),
            "Expenses": st.column_config.NumberColumn(format="$%.2f"),
            "Net": st.column_config.NumberColumn(format="$%.2f"),
        },
    )
    st.bar_chart(df.set_index("Period")[["Income", "Expenses"]])

st.divider()
st.subheader("Spending by category — current period")

txns = db.fetch_transactions(
    fiscal_year=current.fiscal_year, fiscal_period=current.fiscal_period
)
if txns:
    rows = []
    for t in txns:
        if t["amount"] < 0:
            rows.append({"Category": t["category_name"], "Amount": -t["amount"]})
    if rows:
        cat_df = (
            pd.DataFrame(rows)
            .groupby("Category", as_index=False)["Amount"]
            .sum()
            .sort_values("Amount", ascending=False)
        )
        st.dataframe(
            cat_df,
            hide_index=True,
            use_container_width=True,
            column_config={
                "Amount": st.column_config.NumberColumn(format="$%.2f"),
            },
        )
    else:
        st.caption("No expenses recorded for this period yet.")
else:
    st.caption("No transactions in this period.")
