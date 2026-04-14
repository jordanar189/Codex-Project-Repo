"""Tests for the correlation-based R-squared tooling."""
import math
import unittest

import numpy as np
import pandas as pd

from regression_modeling_tool.regression import (
    compute_r_squared,
    count_combinations,
    evaluate_all_combinations,
    results_to_dataframe,
)


def _ols_r_squared(y: np.ndarray, X: np.ndarray) -> float:
    """Reference R-squared from an actual OLS fit with intercept."""
    n = X.shape[0]
    Xc = np.column_stack([np.ones(n), X])
    beta, *_ = np.linalg.lstsq(Xc, y, rcond=None)
    y_hat = Xc @ beta
    ss_res = float(np.sum((y - y_hat) ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    return 1.0 - ss_res / ss_tot


class ComputeRSquaredTests(unittest.TestCase):
    def test_perfect_simple_linear(self):
        x = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        y = 2.0 * x + 1.0
        self.assertAlmostEqual(compute_r_squared(y, x), 1.0, places=10)

    def test_negative_relationship_still_positive_r2(self):
        x = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        y = -3.0 * x + 7.0
        self.assertAlmostEqual(compute_r_squared(y, x), 1.0, places=10)

    def test_matches_ols_simple(self):
        rng = np.random.default_rng(7)
        x = rng.normal(size=80)
        y = 2.5 * x + rng.normal(scale=0.7, size=80)
        self.assertAlmostEqual(
            compute_r_squared(y, x),
            _ols_r_squared(y, x.reshape(-1, 1)),
            places=8,
        )

    def test_matches_ols_multiple(self):
        rng = np.random.default_rng(0)
        n = 150
        x1 = rng.normal(size=n)
        x2 = rng.normal(size=n)
        x3 = rng.normal(size=n)
        y = 3.0 * x1 - 2.0 * x2 + 0.5 * x3 + rng.normal(scale=0.4, size=n)
        X = np.column_stack([x1, x2, x3])
        self.assertAlmostEqual(
            compute_r_squared(y, X),
            _ols_r_squared(y, X),
            places=8,
        )

    def test_handles_collinear_features(self):
        rng = np.random.default_rng(1)
        n = 60
        x1 = rng.normal(size=n)
        x2 = x1 * 2.0 + 0.5  # exactly collinear with x1
        y = 4.0 * x1 + rng.normal(scale=0.3, size=n)
        X = np.column_stack([x1, x2])
        r2 = compute_r_squared(y, X)
        self.assertTrue(0.0 <= r2 <= 1.0)
        # Collinear duplicate shouldn't raise and should roughly match simple R^2.
        self.assertAlmostEqual(r2, compute_r_squared(y, x1), places=6)

    def test_zero_variance_target_is_nan(self):
        y = np.ones(10)
        x = np.arange(10, dtype=float)
        self.assertTrue(math.isnan(compute_r_squared(y, x)))

    def test_zero_variance_feature_is_nan(self):
        y = np.arange(10, dtype=float)
        x = np.ones(10)
        self.assertTrue(math.isnan(compute_r_squared(y, x)))

    def test_shape_mismatch_raises(self):
        with self.assertRaises(ValueError):
            compute_r_squared(np.arange(5, dtype=float), np.arange(6, dtype=float))


class EvaluateAllCombinationsTests(unittest.TestCase):
    def _make_df(self) -> pd.DataFrame:
        rng = np.random.default_rng(42)
        n = 80
        a = rng.normal(size=n)
        b = rng.normal(size=n)
        c = rng.normal(size=n)
        y = 2.0 * a - 1.0 * b + rng.normal(scale=0.25, size=n)
        return pd.DataFrame({"y": y, "a": a, "b": b, "c": c})

    def test_counts_all_subsets(self):
        df = self._make_df()
        results = evaluate_all_combinations(df, "y", ["a", "b", "c"])
        # C(3,1) + C(3,2) + C(3,3) = 3 + 3 + 1 = 7.
        self.assertEqual(len(results), 7)

    def test_results_sorted_descending(self):
        df = self._make_df()
        results = evaluate_all_combinations(df, "y", ["a", "b", "c"])
        r2s = [r2 for _, r2, _ in results]
        self.assertEqual(r2s, sorted(r2s, reverse=True))

    def test_full_model_beats_single_feature(self):
        df = self._make_df()
        results = evaluate_all_combinations(df, "y", ["a", "b", "c"])
        best_combo, best_r2, _ = results[0]
        # The noise-free signal uses a and b, so the winner should include both.
        self.assertIn("a", best_combo)
        self.assertIn("b", best_combo)
        self.assertGreater(best_r2, 0.9)

    def test_max_size_caps_combinations(self):
        df = self._make_df()
        results = evaluate_all_combinations(df, "y", ["a", "b", "c"], max_size=2)
        self.assertEqual(len(results), count_combinations(3, 2))  # 6
        for combo, _, _ in results:
            self.assertLessEqual(len(combo), 2)

    def test_target_cannot_be_feature(self):
        df = self._make_df()
        with self.assertRaises(ValueError):
            evaluate_all_combinations(df, "y", ["y", "a"])

    def test_missing_column_raises(self):
        df = self._make_df()
        with self.assertRaises(KeyError):
            evaluate_all_combinations(df, "y", ["a", "does_not_exist"])

    def test_drops_nan_rows_per_model(self):
        df = self._make_df().copy()
        df.loc[df.index[:5], "a"] = np.nan  # only affects models that use "a"
        results = evaluate_all_combinations(df, "y", ["a", "b", "c"])
        rows_by_model = {combo: n for combo, _, n in results}
        self.assertEqual(rows_by_model[("b",)], len(df))
        self.assertEqual(rows_by_model[("a",)], len(df) - 5)
        self.assertEqual(rows_by_model[("a", "b")], len(df) - 5)


class HelperTests(unittest.TestCase):
    def test_count_combinations_matches_formula(self):
        # 2^k - 1 for k features is sum_{i=1..k} C(k, i).
        self.assertEqual(count_combinations(4), 15)
        self.assertEqual(count_combinations(4, max_size=2), 10)
        self.assertEqual(count_combinations(0), 0)

    def test_results_to_dataframe_schema(self):
        df = pd.DataFrame(
            {"y": [1.0, 2.0, 3.0, 4.0, 5.0], "a": [1.0, 2.0, 3.0, 4.0, 5.0]}
        )
        results = evaluate_all_combinations(df, "y", ["a"])
        table = results_to_dataframe(results)
        self.assertEqual(
            list(table.columns),
            ["Rank", "Model", "Num features", "R-squared", "Rows used"],
        )
        self.assertEqual(table.loc[0, "Rank"], 1)
        self.assertAlmostEqual(table.loc[0, "R-squared"], 1.0, places=10)


if __name__ == "__main__":
    unittest.main()
