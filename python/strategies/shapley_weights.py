"""

Shapley value computation for multi-LLM consensus weighting.

Instead of equal-weight averaging (or trimmed mean), compute each model's
marginal contribution to consensus accuracy using cooperative game theory.
Models that consistently improve consensus get higher weight.

Usage:
    from strategies.shapley_weights import compute_weights, weighted_consensus

    # From historical signals
    weights = compute_weights(signals_db_path="signals.db")

    # Apply to current predictions
    avg = weighted_consensus(probs, model_names, weights)
"""

import sqlite3
import math
from itertools import combinations
from typing import Dict, List, Optional, Tuple


MODEL_NAMES = ["Claude", "GPT", "Gemini", "Grok", "DeepSeek"]


def _coalition_accuracy(
    predictions: List[Dict[str, float]],
    outcomes: List[float],
    coalition: Tuple[str, ...],
) -> float:
    """
    Compute negative MAE for a coalition's average predictions.
    Higher is better (less error = more value).
    """
    if not coalition or not predictions:
        return 0.0

    total_error = 0.0
    count = 0

    for pred, outcome in zip(predictions, outcomes):
        probs = [pred[m] for m in coalition if m in pred]
        if not probs:
            continue
        avg = sum(probs) / len(probs)
        total_error += abs(avg - outcome)
        count += 1

    if count == 0:
        return 0.0

    return -(total_error / count)


def shapley_values(
    predictions: List[Dict[str, float]],
    outcomes: List[float],
    models: Optional[List[str]] = None,
) -> Dict[str, float]:
    """
    Compute exact Shapley values for each model's contribution to consensus.

    Uses the standard formula:
        phi_i = sum over S subset N\\{i} of
            |S|!(|N|-|S|-1)!/|N|! * [v(S union {i}) - v(S)]

    With 5 models this is 2^5 = 32 coalition evaluations.
    """
    models = models or MODEL_NAMES
    n = len(models)
    phi: Dict[str, float] = {m: 0.0 for m in models}

    for model_i in models:
        others = [m for m in models if m != model_i]

        for size in range(0, n):
            for coalition in combinations(others, size):
                v_without = _coalition_accuracy(predictions, outcomes, coalition)
                v_with = _coalition_accuracy(
                    predictions, outcomes, coalition + (model_i,)
                )
                marginal = v_with - v_without

                weight = (
                    math.factorial(size)
                    * math.factorial(n - size - 1)
                    / math.factorial(n)
                )
                phi[model_i] += weight * marginal

    return phi


def normalize_weights(phi: Dict[str, float]) -> Dict[str, float]:
    """
    Convert Shapley values to positive weights summing to 1.0.
    Shifts values so minimum is non-negative, then normalizes.
    """
    if not phi:
        return {}

    min_val = min(phi.values())
    shifted = {m: v - min_val + 1e-8 for m, v in phi.items()}
    total = sum(shifted.values())

    if total < 1e-6:
        n = len(phi)
        return {m: 1.0 / n for m in phi}

    return {m: v / total for m, v in shifted.items()}


def compute_weights(signals_db_path: str = "signals.db") -> Dict[str, float]:
    """
    Load resolved signals from the database and compute Shapley-based weights.

    Falls back to equal weights if insufficient history (<10 resolved signals).
    """
    try:
        conn = sqlite3.connect(signals_db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            """
            SELECT claude_prob, gpt_prob, gemini_prob, grok_prob, deepseek_prob,
                   outcome
            FROM signals
            WHERE outcome IS NOT NULL
            ORDER BY created_at DESC
            LIMIT 500
            """
        )
        rows = cursor.fetchall()
        conn.close()
    except Exception:
        return {m: 1.0 / len(MODEL_NAMES) for m in MODEL_NAMES}

    if len(rows) < 10:
        return {m: 1.0 / len(MODEL_NAMES) for m in MODEL_NAMES}

    col_map = {
        "Claude": "claude_prob",
        "GPT": "gpt_prob",
        "Gemini": "gemini_prob",
        "Grok": "grok_prob",
        "DeepSeek": "deepseek_prob",
    }

    predictions = []
    outcomes = []

    for row in rows:
        pred = {}
        for model, col in col_map.items():
            val = row[col]
            if val is not None:
                pred[model] = float(val)
        if len(pred) >= 3:
            predictions.append(pred)
            outcomes.append(float(row["outcome"]))

    if len(predictions) < 10:
        return {m: 1.0 / len(MODEL_NAMES) for m in MODEL_NAMES}

    phi = shapley_values(predictions, outcomes)
    return normalize_weights(phi)


def weighted_consensus(
    probs: List[float],
    model_names: List[str],
    weights: Optional[Dict[str, float]] = None,
) -> float:
    """
    Compute weighted consensus probability.

    If weights are provided, uses Shapley-weighted average.
    Otherwise falls back to trimmed mean (current behavior).
    """
    if weights is None or not weights:
        if len(probs) >= 5:
            trimmed = sorted(probs)[1:-1]
        else:
            trimmed = probs
        return sum(trimmed) / len(trimmed) if trimmed else 0.5

    total_weight = 0.0
    weighted_sum = 0.0

    for prob, name in zip(probs, model_names):
        w = weights.get(name, 0.0)
        weighted_sum += prob * w
        total_weight += w

    if total_weight < 1e-6:
        return sum(probs) / len(probs) if probs else 0.5

    return weighted_sum / total_weight
