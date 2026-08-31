"""Comparison engine: selection, quality, arithmetic, aggregations (§7)."""

from rent_seekers.compare.aggregate import summarize_comparisons
from rent_seekers.compare.calculate import build_comparison
from rent_seekers.compare.engine import enrich_bundle_comparisons, write_comparison_artifacts
from rent_seekers.compare.explain import explain_comparison, format_explain_text
from rent_seekers.compare.quality import assess_quality, quality_rank
from rent_seekers.compare.select import (
    best_by_development,
    rank_comparisons,
    select_best_comparison,
)

__all__ = [
    "assess_quality",
    "best_by_development",
    "build_comparison",
    "enrich_bundle_comparisons",
    "explain_comparison",
    "format_explain_text",
    "quality_rank",
    "rank_comparisons",
    "select_best_comparison",
    "summarize_comparisons",
    "write_comparison_artifacts",
]
