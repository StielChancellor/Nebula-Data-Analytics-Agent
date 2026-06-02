"""Stats library tests — deterministic methods with known answers."""
import pytest

# Skip the whole module if numpy/scipy aren't installed (CI installs [dev,stats]).
pytest.importorskip("numpy")
pytest.importorskip("scipy")

from insnav_agents import stats


class TestSummary:
    def test_known_values(self):
        r = stats.summary_stats([2, 4, 6, 8, 10])
        assert r["result"]["n"] == 5
        assert r["result"]["mean"] == 6.0
        assert r["result"]["median"] == 6.0
        assert r["result"]["min"] == 2.0 and r["result"]["max"] == 10.0
        assert r["confidence"] == 1.0

    def test_small_sample_caveat(self):
        r = stats.summary_stats([1, 2, 3])
        assert any("small sample" in c for c in r["caveats"])

    def test_empty(self):
        r = stats.summary_stats([])
        assert r["confidence"] == 0.0


class TestSignificance:
    def test_clearly_different_groups_significant(self):
        a = [10, 11, 9, 10, 12, 11, 10, 9, 11, 10, 12, 11, 10, 9, 11]
        b = [20, 21, 19, 20, 22, 21, 20, 19, 21, 20, 22, 21, 20, 19, 21]
        r = stats.significance_test(a, b)
        assert r["result"]["significant"] is True
        assert r["result"]["p_value"] < 0.05
        assert abs(r["result"]["effect_size_cohens_d"]) > 2  # huge effect

    def test_identical_groups_not_significant(self):
        a = [5, 6, 7, 5, 6, 7, 5, 6, 7, 5, 6, 7, 5, 6, 7]
        r = stats.significance_test(a, list(a))
        assert r["result"]["significant"] is False

    def test_auto_picks_mannwhitney_for_small_samples(self):
        r = stats.significance_test([1, 2, 3], [4, 5, 6])
        assert r["method_used"] == "mann_whitney_u"

    def test_too_few_values(self):
        r = stats.significance_test([1], [2])
        assert r["confidence"] == 0.0


class TestCorrelation:
    def test_perfect_positive(self):
        r = stats.correlation([1, 2, 3, 4, 5], [2, 4, 6, 8, 10])
        assert r["result"]["r"] == pytest.approx(1.0, abs=1e-9)
        assert r["result"]["significant"] is True

    def test_perfect_negative(self):
        r = stats.correlation([1, 2, 3, 4, 5], [10, 8, 6, 4, 2])
        assert r["result"]["r"] == pytest.approx(-1.0, abs=1e-9)

    def test_always_warns_not_causation(self):
        r = stats.correlation([1, 2, 3, 4], [1, 3, 2, 4])
        assert any("causation" in c for c in r["caveats"])


class TestAnomaly:
    def test_detects_obvious_outlier(self):
        vals = [10, 11, 9, 10, 12, 11, 10, 9, 11, 10, 200]  # 200 is the outlier
        r = stats.detect_anomalies(vals, z_threshold=2.5)
        assert r["result"]["count"] >= 1
        assert any(a["value"] == 200.0 for a in r["result"]["anomalies"])

    def test_no_anomalies_in_uniform(self):
        r = stats.detect_anomalies([5, 5, 5, 5, 5])
        assert r["result"].get("anomalies", []) == [] or r["result"].get("count", 0) == 0


class TestForecast:
    def test_linear_series_continues_trend(self):
        r = stats.forecast([1, 2, 3, 4, 5, 6, 7, 8], periods=3)
        preds = r["result"]["predictions"]
        assert len(preds) == 3
        # A clean +1/step linear series → next points ~9, 10, 11
        assert preds[0]["forecast"] == pytest.approx(9.0, abs=0.5)
        assert preds[2]["forecast"] > preds[0]["forecast"]  # increasing
        assert r["result"]["trend_per_period"] == pytest.approx(1.0, abs=0.3)

    def test_predictions_carry_uncertainty_band(self):
        r = stats.forecast([10, 12, 11, 13, 12, 14, 13, 15], periods=2)
        for p in r["result"]["predictions"]:
            assert p["low"] <= p["forecast"] <= p["high"]
        assert any("band" in c or "assumes" in c for c in r["caveats"])

    def test_too_short(self):
        r = stats.forecast([1, 2], periods=3)
        assert r["confidence"] == 0.0


class TestRegression:
    def test_perfect_line(self):
        r = stats.linear_regression([1, 2, 3, 4, 5], [2, 4, 6, 8, 10])
        assert r["result"]["slope"] == pytest.approx(2.0, abs=1e-6)
        assert r["result"]["r_squared"] == pytest.approx(1.0, abs=1e-6)

    def test_too_few_points(self):
        r = stats.linear_regression([1, 2], [2, 4])
        assert r["confidence"] == 0.0


class TestDiffInDifferences:
    def test_basic_2x2(self):
        # treated rose 30, control rose 10 → DiD = 20
        r = stats.diff_in_differences(pre_treatment=[100], post_treatment=[130],
                                      pre_control=[50], post_control=[60])
        assert r["result"]["did_estimate"] == pytest.approx(20.0)
        assert r["result"]["treatment_change"] == pytest.approx(30.0)

    def test_accepts_lists_and_averages(self):
        r = stats.diff_in_differences(pre_treatment=[10, 20], post_treatment=[40, 40],
                                      pre_control=[10, 10], post_control=[10, 10])
        # treated mean 15→40 (Δ25), control 10→10 (Δ0) → DiD 25
        assert r["result"]["did_estimate"] == pytest.approx(25.0)

    def test_missing_cell_is_graceful(self):
        r = stats.diff_in_differences(pre_treatment=[], post_treatment=[1],
                                      pre_control=[1], post_control=[1])
        assert r["confidence"] == 0.0


class TestDispatch:
    def test_run_analysis_routes(self):
        r = stats.run_analysis("summary", values=[1, 2, 3, 4, 5])
        assert r["method_used"] == "summary_stats"

    def test_regression_and_did_registered(self):
        assert stats.run_analysis("regression", x=[1, 2, 3], y=[1, 2, 3])["method_used"] == "ols_regression"
        assert stats.run_analysis("did", pre_treatment=[1], post_treatment=[2],
                                  pre_control=[1], post_control=[1])["method_used"] == "diff_in_differences"

    def test_unknown_method(self):
        r = stats.run_analysis("teleport", values=[1, 2, 3])
        assert r["confidence"] == 0.0
        assert any("unknown" in c for c in r["caveats"])

    def test_bad_args(self):
        r = stats.run_analysis("forecast", wrong_kwarg=123)
        assert r["confidence"] == 0.0
