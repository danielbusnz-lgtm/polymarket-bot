"""Tests for Shapley value model weighting."""

from strategies.shapley_weights import (
    shapley_values,
    normalize_weights,
    weighted_consensus,
    _coalition_accuracy,
)


def test_shapley_efficiency_axiom():
    """Shapley values must sum to v(N) - v(empty)."""
    predictions = [
        {"A": 0.7, "B": 0.6, "C": 0.8},
        {"A": 0.3, "B": 0.4, "C": 0.2},
        {"A": 0.9, "B": 0.5, "C": 0.7},
    ]
    outcomes = [1.0, 0.0, 1.0]

    phi = shapley_values(predictions, outcomes, models=["A", "B", "C"])

    grand = _coalition_accuracy(predictions, outcomes, ("A", "B", "C"))
    empty = _coalition_accuracy(predictions, outcomes, ())

    assert abs(sum(phi.values()) - (grand - empty)) < 1e-6


def test_better_model_gets_higher_value():
    """A model closer to truth should get higher Shapley value."""
    predictions = [
        {"good": 0.9, "bad": 0.5},
        {"good": 0.1, "bad": 0.5},
        {"good": 0.8, "bad": 0.5},
    ]
    outcomes = [1.0, 0.0, 1.0]

    phi = shapley_values(predictions, outcomes, models=["good", "bad"])
    assert phi["good"] > phi["bad"]


def test_normalize_sums_to_one():
    """Normalized weights must sum to 1.0."""
    phi = {"A": -0.05, "B": -0.02, "C": -0.03}
    weights = normalize_weights(phi)
    assert abs(sum(weights.values()) - 1.0) < 1e-6
    assert all(w > 0 for w in weights.values())


def test_normalize_equal_values():
    """Equal Shapley values produce equal weights."""
    phi = {"A": -0.03, "B": -0.03, "C": -0.03}
    weights = normalize_weights(phi)
    for w in weights.values():
        assert abs(w - 1.0 / 3) < 1e-6


def test_weighted_consensus_favors_better_model():
    """Weighted consensus should lean toward higher-weighted models."""
    probs = [0.9, 0.1]
    names = ["good", "bad"]
    weights = {"good": 0.8, "bad": 0.2}
    result = weighted_consensus(probs, names, weights)
    assert result > 0.5


def test_weighted_consensus_trimmed_mean_fallback():
    """Without weights, should use trimmed mean."""
    probs = [0.1, 0.5, 0.5, 0.5, 0.9]
    result = weighted_consensus(probs, ["A", "B", "C", "D", "E"])
    assert abs(result - 0.5) < 1e-6


def test_weighted_consensus_no_models():
    """Empty input should return 0.5."""
    result = weighted_consensus([], [])
    assert result == 0.5


def test_symmetry_axiom():
    """Two identical models should get the same Shapley value."""
    predictions = [
        {"A": 0.7, "B": 0.7},
        {"A": 0.3, "B": 0.3},
    ]
    outcomes = [1.0, 0.0]
    phi = shapley_values(predictions, outcomes, models=["A", "B"])
    assert abs(phi["A"] - phi["B"]) < 1e-6
