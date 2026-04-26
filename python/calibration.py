"""Isotonic calibration for LLM consensus probabilities.

Why this exists: frontier LLMs are systematically overconfident on prediction
markets — at 95% claimed confidence, the best model in the KalshiBench eval
(Claude Opus 4.5) is correct only 70% of the time. Multi-model averaging
narrows the gap but does not close it. The standard fix is post-hoc
isotonic regression on (raw_consensus_prob, resolved_outcome) pairs.

We require at least MIN_SAMPLES resolved signals before applying any
non-identity calibration; below that threshold we pass raw probs through
unchanged so the bot keeps trading while the dataset grows.

Persisted in bot.db as a list of (knot_x, knot_y) pairs; predict() does
piecewise-linear interpolation, clipped to [Y_MIN, Y_MAX] so Kelly sizing
never divides by zero.
"""

from __future__ import annotations

import json
import time
from typing import Any, Callable, Iterable

from sklearn.isotonic import IsotonicRegression


MIN_SAMPLES = 30
Y_MIN = 0.02
Y_MAX = 0.98
DEFAULT_BINS = 10


class Calibrator:
    __slots__ = ("knots_x", "knots_y", "n_samples", "fitted_at")

    def __init__(self, knots_x: list[float], knots_y: list[float],
                 n_samples: int, fitted_at: float | None = None) -> None:
        if len(knots_x) != len(knots_y):
            raise ValueError("knots_x and knots_y must be same length")
        self.knots_x = list(knots_x)
        self.knots_y = list(knots_y)
        self.n_samples = n_samples
        self.fitted_at = fitted_at if fitted_at is not None else time.time()

    @property
    def is_identity(self) -> bool:
        return self.n_samples == 0

    @classmethod
    def identity(cls) -> "Calibrator":
        return cls(knots_x=[], knots_y=[], n_samples=0)

    @classmethod
    def from_resolved(cls, samples: Iterable[tuple[float, int]]) -> "Calibrator":
        pairs = [(float(p), int(y)) for p, y in samples]
        if len(pairs) < MIN_SAMPLES:
            return cls.identity()

        xs = [p for p, _ in pairs]
        ys = [y for _, y in pairs]

        iso = IsotonicRegression(out_of_bounds="clip", y_min=Y_MIN, y_max=Y_MAX)
        iso.fit(xs, ys)

        knots_x = [float(x) for x in iso.X_thresholds_]
        knots_y = [float(y) for y in iso.y_thresholds_]
        return cls(knots_x=knots_x, knots_y=knots_y, n_samples=len(pairs))

    def predict(self, p: float) -> float:
        if self.is_identity:
            return min(max(float(p), 0.0), 1.0)

        x = float(p)
        if x <= self.knots_x[0]:
            return max(self.knots_y[0], Y_MIN)
        if x >= self.knots_x[-1]:
            return min(self.knots_y[-1], Y_MAX)

        # Piecewise linear interpolation between the two surrounding knots.
        for i in range(1, len(self.knots_x)):
            if x <= self.knots_x[i]:
                x0, x1 = self.knots_x[i - 1], self.knots_x[i]
                y0, y1 = self.knots_y[i - 1], self.knots_y[i]
                if x1 == x0:
                    return min(max(y1, Y_MIN), Y_MAX)
                t = (x - x0) / (x1 - x0)
                return min(max(y0 + t * (y1 - y0), Y_MIN), Y_MAX)
        return min(max(self.knots_y[-1], Y_MIN), Y_MAX)


# ---------------------------------------------------------------------------
# Persistence (bot.db)
# ---------------------------------------------------------------------------


def _ensure_table(conn: Any) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS calibration (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            fitted_at   REAL NOT NULL,
            n_samples   INTEGER NOT NULL,
            knots_json  TEXT NOT NULL
        )
    """)


def save(conn: Any, calibrator: Calibrator) -> None:
    _ensure_table(conn)
    knots_json = json.dumps([calibrator.knots_x, calibrator.knots_y])
    conn.execute(
        "INSERT INTO calibration (fitted_at, n_samples, knots_json) VALUES (?, ?, ?)",
        (calibrator.fitted_at, calibrator.n_samples, knots_json),
    )
    conn.commit()


def load_latest(conn: Any) -> Calibrator:
    _ensure_table(conn)
    row = conn.execute(
        "SELECT fitted_at, n_samples, knots_json FROM calibration "
        "ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if row is None or row["n_samples"] < MIN_SAMPLES:
        return Calibrator.identity()
    knots_x, knots_y = json.loads(row["knots_json"])
    return Calibrator(
        knots_x=knots_x, knots_y=knots_y,
        n_samples=row["n_samples"], fitted_at=row["fitted_at"],
    )


# ---------------------------------------------------------------------------
# End-to-end fit using the existing signal/bot connections
# ---------------------------------------------------------------------------


def _fetch_resolved(get_signals_conn: Callable[[], Any]) -> list[tuple[float, int]]:
    with get_signals_conn() as conn:
        rows = conn.execute(
            "SELECT avg_prob, direction, outcome FROM signals "
            "WHERE resolved = 1 AND outcome IS NOT NULL AND avg_prob IS NOT NULL"
        ).fetchall()
    samples: list[tuple[float, int]] = []
    for r in rows:
        # avg_prob is the model's P(YES). Convert resolution to "did the YES side win?"
        won_yes = 1 if r["outcome"] == "YES" else 0
        samples.append((float(r["avg_prob"]), won_yes))
    return samples


def fit_and_save(
    get_signals_conn: Callable[[], Any],
    get_bot_conn: Callable[[], Any],
) -> Calibrator:
    samples = _fetch_resolved(get_signals_conn)
    iso = Calibrator.from_resolved(samples)
    if iso.is_identity:
        return iso
    with get_bot_conn() as conn:
        save(conn, iso)
    return iso


# ---------------------------------------------------------------------------
# Reliability diagram (for `report`)
# ---------------------------------------------------------------------------


def reliability_diagram(
    samples: Iterable[tuple[float, int]],
    n_bins: int = DEFAULT_BINS,
) -> dict[int, dict[str, float]]:
    """Bin samples by predicted prob into n_bins equal-width buckets.

    Returns a dict keyed by bin index (0..n_bins-1) with:
      bin_low, bin_high, n, accuracy, mean_pred, gap (mean_pred - accuracy)
    """
    bins: dict[int, list[tuple[float, int]]] = {i: [] for i in range(n_bins)}
    width = 1.0 / n_bins
    for p, y in samples:
        idx = min(int(p / width), n_bins - 1)
        bins[idx].append((float(p), int(y)))

    out: dict[int, dict[str, float]] = {}
    for i, items in bins.items():
        lo = i * width
        hi = (i + 1) * width
        if not items:
            out[i] = {"bin_low": lo, "bin_high": hi, "n": 0,
                      "accuracy": 0.0, "mean_pred": 0.0, "gap": 0.0}
            continue
        n = len(items)
        accuracy = sum(y for _, y in items) / n
        mean_pred = sum(p for p, _ in items) / n
        out[i] = {
            "bin_low": lo, "bin_high": hi, "n": n,
            "accuracy": accuracy, "mean_pred": mean_pred,
            "gap": mean_pred - accuracy,
        }
    return out
