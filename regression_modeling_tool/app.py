"""Streamlit UI for the regression modeling tool.

Run with:
    streamlit run regression_modeling_tool/app.py
"""
from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd
import streamlit as st

# Allow ``streamlit run regression_modeling_tool/app.py`` from the repo root.
_PKG_DIR = Path(__file__).resolve().parent
if str(_PKG_DIR.parent) not in sys.path:
    sys.path.insert(0, str(_PKG_DIR.parent))

from regression_modeling_tool.regression import (  # noqa: E402
    count_combinations,
    evaluate_all_combinations,
    results_to_dataframe,
)


PREVIEW_MIN = 10
PREVIEW_MAX = 100
PREVIEW_DEFAULT = 50


def _load_dataset(uploaded_file) -> pd.DataFrame:
    name = uploaded_file.name.lower()
    if name.endswith(".csv"):
        return pd.read_csv(uploaded_file)
    if name.endswith((".xlsx", ".xls")):
        return pd.read_excel(uploaded_file)
    raise ValueError(f"Unsupported file type: {uploaded_file.name}")


def main() -> None:
    st.set_page_config(
        page_title="Regression Modeling Tool",
        layout="wide",
        page_icon=None,
    )

    st.title("Regression Modeling Tool")
    st.write(
        "Upload a CSV or Excel dataset, pick your target and candidate "
        "predictors, and compare the R-squared of every possible linear "
        "model (single-variable or multiple regression)."
    )

    uploaded = st.file_uploader(
        "Dataset (CSV or Excel)",
        type=["csv", "xlsx", "xls"],
    )
    if uploaded is None:
        st.info("Upload a file to begin.")
        return

    try:
        df = _load_dataset(uploaded)
    except Exception as exc:  # pragma: no cover - user-facing error surface
        st.error(f"Could not read file: {exc}")
        return

    if df.empty:
        st.error("The uploaded file has no rows.")
        return

    st.subheader("Preview")
    preview_rows = st.slider(
        "Preview rows",
        min_value=PREVIEW_MIN,
        max_value=PREVIEW_MAX,
        value=min(PREVIEW_DEFAULT, max(PREVIEW_MIN, len(df))),
        help="How many rows to show in the preview table.",
    )
    st.dataframe(df.head(preview_rows), use_container_width=True)
    st.caption(f"Dataset shape: {len(df):,} rows \u00d7 {len(df.columns)} columns.")

    all_cols = list(df.columns)
    numeric_cols = df.select_dtypes(include="number").columns.tolist()

    if not numeric_cols:
        st.error("No numeric columns found. Regression needs numeric data.")
        return

    st.subheader("Column roles")
    left, right = st.columns(2)

    with left:
        target = st.selectbox(
            "Independent variable (target)",
            options=numeric_cols,
            help=(
                "The column you want to explain. R-squared is computed "
                "against this column."
            ),
        )
        label_options = ["(none)"] + [c for c in all_cols if c != target]
        label_col = st.selectbox(
            "Feature / label column (optional)",
            options=label_options,
            help=(
                "A descriptive column (e.g. name or ID) that should be "
                "excluded from modeling."
            ),
        )

    with right:
        excluded = {target}
        if label_col != "(none)":
            excluded.add(label_col)
        feature_candidates = [c for c in numeric_cols if c not in excluded]
        non_numeric = [c for c in all_cols if c not in numeric_cols and c not in excluded]
        features = st.multiselect(
            "Dependent variables (candidate predictors)",
            options=feature_candidates,
            default=feature_candidates,
            help="Every non-empty subset of these will be evaluated.",
        )
        if non_numeric:
            st.caption(
                "Non-numeric columns are hidden from predictor choices: "
                + ", ".join(non_numeric)
            )

    if not features:
        st.info("Select at least one dependent variable to run the analysis.")
        return

    with st.expander("Advanced options", expanded=False):
        max_size = st.slider(
            "Maximum features per model",
            min_value=1,
            max_value=len(features),
            value=min(len(features), 5),
            help=(
                "Cap the combination size.  With k features there are "
                "2^k - 1 possible models, so capping keeps large selections "
                "responsive."
            ),
        )
        top_n = st.number_input(
            "Show top N models (0 = all)",
            min_value=0,
            value=50,
            step=10,
        )

    n_combos = count_combinations(len(features), max_size)
    st.caption(f"Will evaluate {n_combos:,} candidate models.")

    if st.button("Run analysis", type="primary"):
        with st.spinner(f"Evaluating {n_combos:,} models..."):
            results = evaluate_all_combinations(
                df,
                target=target,
                features=features,
                max_size=max_size,
            )
        result_df = results_to_dataframe(results)

        if top_n and top_n > 0:
            shown = result_df.head(int(top_n))
        else:
            shown = result_df

        st.subheader("Results (highest R-squared first)")
        st.dataframe(
            shown.style.format({"R-squared": "{:.5f}"}),
            use_container_width=True,
            hide_index=True,
        )

        best_combo, best_r2, _ = results[0]
        st.success(
            f"Best model: **{' + '.join(best_combo)}**  \u2014  "
            f"R\u00b2 = {best_r2:.5f}"
        )

        st.download_button(
            "Download full results (CSV)",
            result_df.to_csv(index=False).encode("utf-8"),
            file_name="regression_results.csv",
            mime="text/csv",
        )


if __name__ == "__main__":
    main()
