"""Inference-language gates for descriptive population-rent outputs."""

from __future__ import annotations

import pytest

from rent_seekers.inference import validate_inference_language


@pytest.mark.parametrize(
    "claim",
    [
        "Recent movers paid $845 more than incumbents in the observed 2023 survey cells.",
        "This is a descriptive difference, not evidence that tenure caused it.",
        "The intervals do not overlap; this remains descriptive only, not a cause.",
    ],
)
def test_descriptive_language_accepts_observation_and_explicit_limits(claim):
    assert validate_inference_language(claim, inference_class="descriptive_only") == claim


@pytest.mark.parametrize(
    "claim",
    [
        "Longer tenure caused lower rent.",
        "Rent regulation leads to a $829 reduction.",
        "The gap is due to regulation.",
        "This is the effect of incumbency.",
    ],
)
def test_descriptive_language_rejects_causal_assertions(claim):
    with pytest.raises(ValueError, match="cannot assert a causal explanation"):
        validate_inference_language(claim, inference_class="descriptive_only")
