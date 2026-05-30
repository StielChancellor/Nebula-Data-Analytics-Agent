"""
Stats / Maths specialist compute (Phase 9).

PRD § 7: the Stats and Maths agents own inferential work. The load-bearing rule
(constraint #1) still holds — the LLM SELECTS the method + inputs; these
DETERMINISTIC functions compute the numbers. (The full vision is LLM-generated
code in a sandbox; fixed, audited methods are a stricter, safer subset and are
what ships first.)

Every method returns a uniform envelope:
    {method_used, result, assumptions_checked, confidence, caveats}

numpy/scipy are imported lazily so importing this module never requires the
[stats] extra; if they're missing at call time, methods return a graceful
"unavailable" envelope instead of crashing.
"""
from __future__ import annotations

import math
from typing import Any

# Significance threshold (α). Methods flag significant = p < ALPHA.
ALPHA = 0.05
# Below this sample size, results carry a small-sample caveat (PRD mitigation #6).
SMALL_SAMPLE = 30


def _envelope(method: str, result: dict[str, Any], *, confidence: float,
              assumptions: list[str] | None = None, caveats: list[str] | None = None) -> dict[str, Any]:
    return {
        "method_used": method,
        "result": result,
        "assumptions_checked": assumptions or [],
        "confidence": round(confidence, 4),
        "caveats": caveats or [],
    }


def _unavailable(method: str) -> dict[str, Any]:
    return _envelope(method, {}, confidence=0.0,
                     caveats=["numerical libraries (numpy/scipy) are not installed in this environment"])


def _np():
    import numpy as np  # lazy
    return np


# ---------- descriptive ----------

def summary_stats(values: list[float]) -> dict[str, Any]:
    try:
        np = _np()
    except Exception:
        return _unavailable("summary_stats")
    a = np.asarray([v for v in values if v is not None], dtype=float)
    if a.size == 0:
        return _envelope("summary_stats", {}, confidence=0.0, caveats=["no numeric values"])
    res = {
        "n": int(a.size),
        "mean": float(np.mean(a)),
        "median": float(np.median(a)),
        "std": float(np.std(a, ddof=1)) if a.size > 1 else 0.0,
        "min": float(np.min(a)),
        "max": float(np.max(a)),
        "p25": float(np.percentile(a, 25)),
        "p75": float(np.percentile(a, 75)),
    }
    caveats = [] if a.size >= SMALL_SAMPLE else [f"small sample (n={a.size}); interpret with care"]
    return _envelope("summary_stats", res, confidence=1.0, assumptions=["values are numeric"], caveats=caveats)


# ---------- significance ----------

def significance_test(group_a: list[float], group_b: list[float], *, kind: str = "auto") -> dict[str, Any]:
    """
    Compare two groups. `kind`: "ttest" (Welch), "mannwhitney", or "auto"
    (Welch if both n>=15 else Mann-Whitney — robust to non-normal small samples).
    """
    try:
        np = _np()
        from scipy import stats as sp
    except Exception:
        return _unavailable("significance_test")

    a = np.asarray([v for v in group_a if v is not None], dtype=float)
    b = np.asarray([v for v in group_b if v is not None], dtype=float)
    if a.size < 2 or b.size < 2:
        return _envelope("significance_test", {}, confidence=0.0, caveats=["need >= 2 values per group"])

    chosen = kind
    if kind == "auto":
        chosen = "ttest" if (a.size >= 15 and b.size >= 15) else "mannwhitney"

    if chosen == "ttest":
        stat, p = sp.ttest_ind(a, b, equal_var=False)  # Welch
        method = "welch_t_test"
        assumptions = ["independent groups", "approx. normal (n>=15) or use mannwhitney"]
    else:
        stat, p = sp.mannwhitneyu(a, b, alternative="two-sided")
        method = "mann_whitney_u"
        assumptions = ["independent groups", "ordinal/continuous"]

    # Cohen's d effect size (pooled).
    pooled = math.sqrt(((a.size - 1) * np.var(a, ddof=1) + (b.size - 1) * np.var(b, ddof=1)) / (a.size + b.size - 2)) or 1e-12
    d = float((np.mean(a) - np.mean(b)) / pooled)
    caveats = []
    if a.size < SMALL_SAMPLE or b.size < SMALL_SAMPLE:
        caveats.append(f"small sample (n_a={a.size}, n_b={b.size})")
    res = {
        "statistic": float(stat),
        "p_value": float(p),
        "significant": bool(p < ALPHA),
        "alpha": ALPHA,
        "mean_a": float(np.mean(a)),
        "mean_b": float(np.mean(b)),
        "effect_size_cohens_d": round(d, 4),
    }
    return _envelope(method, res, confidence=float(1.0 - p) if p < 1 else 0.0,
                     assumptions=assumptions, caveats=caveats)


# ---------- correlation ----------

def correlation(x: list[float], y: list[float]) -> dict[str, Any]:
    try:
        np = _np()
        from scipy import stats as sp
    except Exception:
        return _unavailable("correlation")
    xs, ys = [], []
    for xi, yi in zip(x, y):
        if xi is not None and yi is not None:
            xs.append(float(xi))
            ys.append(float(yi))
    if len(xs) < 3:
        return _envelope("pearson_correlation", {}, confidence=0.0, caveats=["need >= 3 paired points"])
    r, p = sp.pearsonr(xs, ys)
    caveats = ["correlation is not causation"]
    if len(xs) < SMALL_SAMPLE:
        caveats.append(f"small sample (n={len(xs)})")
    res = {"r": float(r), "p_value": float(p), "n": len(xs), "significant": bool(p < ALPHA)}
    return _envelope("pearson_correlation", res, confidence=float(abs(r)), caveats=caveats)


# ---------- anomaly ----------

def detect_anomalies(values: list[float], *, z_threshold: float = 3.0) -> dict[str, Any]:
    try:
        np = _np()
    except Exception:
        return _unavailable("detect_anomalies")
    a = np.asarray([v for v in values if v is not None], dtype=float)
    if a.size < 3:
        return _envelope("zscore_anomaly", {}, confidence=0.0, caveats=["need >= 3 values"])
    mean, std = float(np.mean(a)), float(np.std(a, ddof=1))
    if std == 0:
        return _envelope("zscore_anomaly", {"anomalies": []}, confidence=1.0, caveats=["zero variance — no anomalies"])
    z = (a - mean) / std
    idx = [int(i) for i in np.where(np.abs(z) > z_threshold)[0]]
    res = {
        "anomalies": [{"index": i, "value": float(a[i]), "z_score": round(float(z[i]), 3)} for i in idx],
        "count": len(idx),
        "z_threshold": z_threshold,
    }
    return _envelope("zscore_anomaly", res, confidence=1.0, assumptions=["roughly normal distribution"])


# ---------- forecast ----------

def forecast(series: list[float], *, periods: int = 3) -> dict[str, Any]:
    """
    Forecast the next `periods` points. Uses simple exponential smoothing with a
    linear-trend (Holt) component, implemented in numpy (no statsmodels). Carries
    uncertainty as a naive +/- band from the residual std. PRD §8: predictive
    answers always ship with stated assumptions + a band, never as fact.
    """
    try:
        np = _np()
    except Exception:
        return _unavailable("forecast")
    a = np.asarray([v for v in series if v is not None], dtype=float)
    if a.size < 4:
        return _envelope("holt_linear", {}, confidence=0.0, caveats=["need >= 4 points to forecast"])

    alpha, beta = 0.5, 0.3  # smoothing constants (level, trend)
    level = float(a[0])
    trend = float(a[1] - a[0])
    fitted = [level]
    for t in range(1, a.size):
        prev_level = level
        level = alpha * float(a[t]) + (1 - alpha) * (level + trend)
        trend = beta * (level - prev_level) + (1 - beta) * trend
        fitted.append(prev_level + trend)
    resid = a[1:] - np.asarray(fitted[1:])
    band = float(np.std(resid, ddof=1)) if resid.size > 1 else 0.0

    preds = []
    for h in range(1, periods + 1):
        point = level + h * trend
        preds.append({"h": h, "forecast": round(float(point), 4),
                      "low": round(float(point - 1.96 * band), 4),
                      "high": round(float(point + 1.96 * band), 4)})
    caveats = ["forecast assumes the recent level + trend continue",
               "95% band from in-sample residual std (naive)"]
    if a.size < 12:
        caveats.append(f"short history (n={a.size}); forecast is fragile")
    res = {"horizon": periods, "predictions": preds, "trend_per_period": round(float(trend), 4)}
    # Confidence shrinks as the band grows relative to the level.
    rel = band / (abs(level) + 1e-9)
    return _envelope("holt_linear", res, confidence=float(max(0.0, 1.0 - min(rel, 1.0))),
                     assumptions=["series is roughly evenly spaced in time"], caveats=caveats)


# ---------- dispatch (the LLM picks a method name + params) ----------

METHODS = {
    "summary": summary_stats,
    "significance": significance_test,
    "correlation": correlation,
    "anomaly": detect_anomalies,
    "forecast": forecast,
}


def run_analysis(method: str, **kwargs: Any) -> dict[str, Any]:
    """Run a named analysis. Unknown method → graceful envelope."""
    fn = METHODS.get(method)
    if fn is None:
        return _envelope(method or "unknown", {}, confidence=0.0,
                         caveats=[f"unknown analysis method '{method}'"])
    try:
        return fn(**kwargs)
    except TypeError as e:
        return _envelope(method, {}, confidence=0.0, caveats=[f"bad arguments for '{method}': {e}"])
