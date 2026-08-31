"""Golden replication of HPD's documented 2021 weighted-median variance example."""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from rent_seekers.normalize.nychvs import successive_difference_variance

FIXTURE = (
    Path(__file__).resolve().parents[1] / "fixtures" / "nychvs" / "hpd_2021_citywide_median.json"
)


def test_hpd_published_weighted_median_standard_error_and_interval():
    benchmark = json.loads(FIXTURE.read_text(encoding="utf-8"))
    variance = successive_difference_variance(
        benchmark["point_estimate"],
        benchmark["replicate_medians"],
        multiplier=benchmark["variance_multiplier"],
    )
    standard_error = math.sqrt(variance)
    interval = (
        benchmark["point_estimate"] - 1.96 * standard_error,
        benchmark["point_estimate"] + 1.96 * standard_error,
    )

    assert len(benchmark["replicate_medians"]) == 80
    assert standard_error == pytest.approx(benchmark["expected_standard_error"], abs=1e-10)
    assert interval == pytest.approx(benchmark["expected_confidence_interval_95"], abs=1e-10)
