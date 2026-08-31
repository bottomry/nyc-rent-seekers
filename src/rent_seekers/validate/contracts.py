"""JSON Schema and semantic contract validation for demo/release bundles."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import jsonschema

from rent_seekers.config import project_root
from rent_seekers.money import compute_wedge


def _load_schema(name: str) -> dict[str, Any]:
    path = project_root() / "schemas" / name
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def validate_demo_bundle(path: Path) -> list[str]:
    """Validate embedded demo bundle against schemas + Fulton golden arithmetic."""
    errors: list[str] = []
    with path.open(encoding="utf-8") as fh:
        bundle = json.load(fh)

    schema = _load_schema("demo_bundle.schema.json")
    try:
        jsonschema.validate(instance=bundle, schema=schema)
    except jsonschema.ValidationError as exc:
        errors.append(f"schema: {exc.message}")

    # Semantic: Fulton arithmetic must match generated wedge
    comps = bundle.get("comparisons") or []
    tenants = {t["observation_id"]: t for t in bundle.get("tenant_rent_observations") or []}
    markets = {m["observation_id"]: m for m in bundle.get("market_rent_observations") or []}

    for c in comps:
        t = tenants.get(c["tenant_rent_observation_id"])
        m = markets.get(c["market_rent_observation_id"])
        if not t or not m:
            errors.append(f"comparison {c['comparison_id']} missing observation refs")
            continue
        expected = compute_wedge(t["value"], m["value"])
        if abs(c["monthly_wedge_usd"] - expected.monthly_wedge_usd) > 0.01:
            errors.append(
                f"monthly_wedge mismatch: {c['monthly_wedge_usd']} != {expected.monthly_wedge_usd}"
            )
        if abs(c["annualized_wedge_usd"] - expected.annualized_wedge_usd) > 0.01:
            errors.append("annualized_wedge mismatch")
        if abs(c["percent_below_comparator"] - expected.percent_below_comparator) > 1e-9:
            errors.append("percent_below mismatch")
        if c.get("comparison_quality") == "exact" and t.get("unit_scope") != m.get("unit_scope"):
            errors.append("scope mismatch cannot be exact")
        # NRS-008: no exact-looking value lacks a quality class
        if not c.get("comparison_quality"):
            errors.append(f"comparison {c['comparison_id']} missing comparison_quality")
        if not isinstance(c.get("quality_reasons"), list):
            errors.append(f"comparison {c['comparison_id']} missing quality_reasons")

    # Comparison index present after NRS-008
    idx = bundle.get("comparison_index")
    if idx is not None:
        if not idx.get("best_by_development"):
            errors.append("comparison_index.best_by_development empty")
        if "quality_counts" not in idx:
            errors.append("comparison_index missing quality_counts")

    return errors
