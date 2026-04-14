"""Fast correlation-based R-squared evaluation across feature combinations.

The "simple" shortcut the user asked for:
    - For a single feature:   R^2 = corr(x, y) ** 2
    - For multiple features:  R^2 = r_xy' @ R_xx^-1 @ r_xy
      (the squared multiple correlation coefficient).  This is mathematically
      equivalent to the OLS coefficient of determination but is computed from
      the correlation matrix alone, so it avoids the cost of fitting a full
      linear regression for every candidate model.
"""
from __future__ import annotations

from itertools import combinations
from math import comb
from typing import Iterable, List, Sequence, Tuple

import numpy as np
import pandas as pd


ModelResult = Tuple[Tuple[str, ...], float, int]


def compute_r_squared(y: np.ndarray, X: np.ndarray) -> float:
    """Return R^2 for regressing ``y`` on the columns of ``X``.

    Uses correlations only, which matches the OLS R^2 for a linear model with
    an intercept.  The returned value is clamped to ``[0.0, 1.0]`` to absorb
    tiny numerical overshoots from the matrix inverse.

    Parameters
    ----------
    y:
        1-D array of the target (length ``n``).
    X:
        2-D array of shape ``(n, k)``.  A 1-D array of length ``n`` is
        accepted and reshaped to a single-column matrix.
    """
    y = np.asarray(y, dtype=float).ravel()
    X = np.asarray(X, dtype=float)
    if X.ndim == 1:
        X = X.reshape(-1, 1)

    if y.shape[0] != X.shape[0]:
        raise ValueError(
            f"y has {y.shape[0]} rows but X has {X.shape[0]}; they must match."
        )
    if X.shape[0] < 2:
        return float("nan")

    # Degenerate target: no variance -> R^2 undefined.
    if np.nanstd(y) == 0:
        return float("nan")

    # Drop columns with zero variance (their correlations are undefined).
    col_std = np.nanstd(X, axis=0)
    keep = col_std > 0
    if not np.any(keep):
        return float("nan")
    X = X[:, keep]

    if X.shape[1] == 1:
        r = np.corrcoef(X[:, 0], y)[0, 1]
        if np.isnan(r):
            return float("nan")
        return float(max(0.0, min(1.0, r * r)))

    # Correlations between each feature and the target.
    r_xy = np.array(
        [np.corrcoef(X[:, i], y)[0, 1] for i in range(X.shape[1])]
    )
    if np.any(np.isnan(r_xy)):
        return float("nan")

    # Feature-to-feature correlation matrix.
    R_xx = np.corrcoef(X, rowvar=False)

    try:
        R_inv = np.linalg.inv(R_xx)
    except np.linalg.LinAlgError:
        # Collinear features -> fall back to Moore-Penrose pseudoinverse.
        R_inv = np.linalg.pinv(R_xx)

    r2 = float(r_xy @ R_inv @ r_xy)
    return max(0.0, min(1.0, r2))


def evaluate_all_combinations(
    df: pd.DataFrame,
    target: str,
    features: Sequence[str],
    min_size: int = 1,
    max_size: int | None = None,
) -> List[ModelResult]:
    """Evaluate every feature subset and return results sorted by R^2 desc.

    Parameters
    ----------
    df:
        DataFrame containing ``target`` and all ``features``.
    target:
        Name of the column to regress on (user's "independent variable").
    features:
        Candidate predictor columns (user's "dependent variables").
    min_size, max_size:
        Inclusive bounds on the subset size.  Defaults span ``1..len(features)``.

    Returns
    -------
    list of ``(feature_tuple, r_squared, n_used)``
        ``n_used`` is the number of non-null rows available for that model.
        Entries with NaN R^2 are kept at the bottom of the list.
    """
    features = list(features)
    if target in features:
        raise ValueError(f"Target '{target}' cannot also be a feature.")

    missing = [c for c in [target, *features] if c not in df.columns]
    if missing:
        raise KeyError(f"Columns not found in dataframe: {missing}")

    if max_size is None:
        max_size = len(features)
    max_size = min(max_size, len(features))
    min_size = max(1, min_size)
    if min_size > max_size:
        return []

    results: List[ModelResult] = []
    for size in range(min_size, max_size + 1):
        for combo in combinations(features, size):
            subset = df[[target, *combo]].dropna()
            n_used = len(subset)
            if n_used < 2:
                results.append((combo, float("nan"), n_used))
                continue
            y = subset[target].to_numpy(dtype=float)
            X = subset[list(combo)].to_numpy(dtype=float)
            r2 = compute_r_squared(y, X)
            results.append((combo, r2, n_used))

    def _sort_key(item: ModelResult) -> Tuple[float, int]:
        _, r2, _ = item
        # NaN R^2 sinks to the bottom regardless of sort direction.
        return (float("-inf") if np.isnan(r2) else r2, 0)

    results.sort(key=_sort_key, reverse=True)
    return results


def count_combinations(n_features: int, max_size: int | None = None) -> int:
    """Count feature subsets of size 1..max_size (default: all)."""
    if max_size is None:
        max_size = n_features
    max_size = min(max_size, n_features)
    return sum(comb(n_features, k) for k in range(1, max_size + 1))


def results_to_dataframe(results: Iterable[ModelResult]) -> pd.DataFrame:
    """Turn ``evaluate_all_combinations`` output into a tidy DataFrame."""
    rows = []
    for rank, (combo, r2, n_used) in enumerate(results, start=1):
        rows.append(
            {
                "Rank": rank,
                "Model": " + ".join(combo),
                "Num features": len(combo),
                "R-squared": r2,
                "Rows used": n_used,
            }
        )
    return pd.DataFrame(
        rows,
        columns=["Rank", "Model", "Num features", "R-squared", "Rows used"],
    )
