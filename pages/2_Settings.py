"""Settings — manage categories, rules, and fiscal calendar anchor."""

from __future__ import annotations

from datetime import date, datetime

import pandas as pd
import streamlit as st

from budgeting import db

st.set_page_config(page_title="Settings", page_icon="⚙️", layout="wide")
db.init_db()

st.title("⚙️ Settings")

cal_tab, cat_tab, rule_tab = st.tabs(
    ["Fiscal calendar", "Categories", "Categorization rules"]
)

# ---------------- Fiscal calendar ----------------

with cal_tab:
    st.subheader("Fiscal calendar anchor")
    st.caption(
        "The fiscal year is 13 periods × 4 weeks (364 days). Set the start date "
        "of any past, present, or future fiscal year — all periods are computed "
        "from this anchor."
    )
    current_anchor = db.get_setting("fiscal_year_start") or "2024-01-07"
    try:
        anchor_default = datetime.strptime(current_anchor, "%Y-%m-%d").date()
    except ValueError:
        anchor_default = date(2024, 1, 7)
    new_anchor = st.date_input("Fiscal year start date", value=anchor_default)
    if st.button("Save anchor"):
        db.set_setting("fiscal_year_start", new_anchor.isoformat())
        st.success(f"Anchor set to {new_anchor.isoformat()}.")
        st.caption(
            "Note: existing transactions keep their stored period until "
            "re-imported."
        )

    st.divider()
    st.subheader("Default amount sign convention")
    sign = db.get_setting("amount_sign_convention") or "income_positive"
    new_sign = st.radio(
        "How are amounts signed in your typical CSV?",
        options=["income_positive", "expenses_positive"],
        index=0 if sign == "income_positive" else 1,
        format_func=lambda x: (
            "Positive = income (deposit)"
            if x == "income_positive"
            else "Positive = expense (debit)"
        ),
    )
    if st.button("Save sign convention"):
        db.set_setting("amount_sign_convention", new_sign)
        st.success("Saved.")

# ---------------- Categories ----------------

with cat_tab:
    st.subheader("Expense categories")
    cats = db.list_categories()
    df = pd.DataFrame(
        [
            {
                "ID": c["id"],
                "Name": c["name"],
                "Default": "Yes" if c["is_default"] else "No",
            }
            for c in cats
        ]
    )
    st.dataframe(df, hide_index=True, use_container_width=True)

    with st.expander("Add a new category"):
        with st.form("add_category"):
            new_name = st.text_input("Category name")
            if st.form_submit_button("Add", type="primary"):
                if not new_name.strip():
                    st.error("Name cannot be empty.")
                else:
                    db.add_category(new_name.strip())
                    st.success(f"Added category '{new_name.strip()}'.")
                    st.rerun()

    with st.expander("Rename a category"):
        with st.form("rename_category"):
            target = st.selectbox(
                "Category",
                options=[c["name"] for c in cats],
                key="rename_target",
            )
            new_label = st.text_input("New name")
            if st.form_submit_button("Rename"):
                target_row = next((c for c in cats if c["name"] == target), None)
                if target_row and new_label.strip():
                    db.rename_category(target_row["id"], new_label.strip())
                    st.success(f"Renamed '{target}' to '{new_label.strip()}'.")
                    st.rerun()

    with st.expander("Delete a non-default category"):
        deletable = [c for c in cats if not c["is_default"]]
        if not deletable:
            st.caption("All current categories are default and cannot be deleted.")
        else:
            with st.form("delete_category"):
                target = st.selectbox(
                    "Category to delete",
                    options=[c["name"] for c in deletable],
                )
                if st.form_submit_button("Delete", type="primary"):
                    target_row = next(
                        (c for c in deletable if c["name"] == target), None
                    )
                    if target_row:
                        try:
                            db.delete_category(target_row["id"])
                            st.success(f"Deleted '{target}'.")
                            st.rerun()
                        except ValueError as exc:
                            st.error(str(exc))

# ---------------- Rules ----------------

with rule_tab:
    st.subheader("Categorization rules")
    st.caption(
        "Each rule maps a substring of the merchant name (case-insensitive) to a "
        "category. The longest matching pattern wins, so you can layer broad "
        "and specific rules together."
    )
    rules = db.list_rules()
    if rules:
        rules_df = pd.DataFrame(
            [
                {
                    "ID": r["id"],
                    "Pattern": r["merchant_pattern"],
                    "Category": r["category_name"],
                }
                for r in rules
            ]
        )
        st.dataframe(rules_df, hide_index=True, use_container_width=True)
    else:
        st.info("No rules yet. Add one below or create rules during review.")

    cats = db.list_categories()
    cat_lookup = {c["name"]: c["id"] for c in cats if c["name"] != "Uncategorized"}

    with st.expander("Add a rule"):
        with st.form("add_rule"):
            pattern = st.text_input(
                "Merchant substring (e.g. 'starbucks', 'shell oil')"
            )
            chosen = st.selectbox("Category", options=list(cat_lookup.keys()))
            if st.form_submit_button("Add rule", type="primary"):
                if not pattern.strip():
                    st.error("Pattern cannot be empty.")
                else:
                    db.add_rule(pattern.strip(), cat_lookup[chosen])
                    st.success(
                        f"Rule added: '{pattern.strip().lower()}' → {chosen}"
                    )
                    st.rerun()

    if rules:
        with st.expander("Delete a rule"):
            with st.form("delete_rule"):
                target = st.selectbox(
                    "Rule",
                    options=[
                        f"{r['merchant_pattern']} → {r['category_name']}"
                        for r in rules
                    ],
                )
                if st.form_submit_button("Delete"):
                    idx = [
                        f"{r['merchant_pattern']} → {r['category_name']}"
                        for r in rules
                    ].index(target)
                    db.delete_rule(rules[idx]["id"])
                    st.success("Rule deleted.")
                    st.rerun()
