"""Newest-authoritative tenant-rent selection (NRS-005).

Rules (spec §5):
1. Retain both PDF and structured Open Data observations.
2. Choose the newest authoritative observation per development.
3. Never overwrite a newer PDF value with an older CSV value.
4. No low-confidence PDF row silently becomes current.
5. A failed/missing PDF parse leaves the older valid structured value
   visible and flagged stale when a newer PDF vintage is known.
"""

from __future__ import annotations

from collections import Counter
from datetime import date
from typing import Any


def _period_date(obs: dict[str, Any]) -> date | None:
    raw = obs.get("period_start") or obs.get("data_as_of")
    if not raw:
        return None
    s = str(raw)[:10]
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def _is_pdf(obs: dict[str, Any]) -> bool:
    art = obs.get("source_artifact_id") or ""
    sid = obs.get("source_id") or ""
    oid = obs.get("observation_id") or ""
    return (
        art.startswith("nycha-ddb-pdf")
        or sid == "nycha_ddb_pdf"
        or (":avg-gross-rent:" in oid and ":open-data" not in oid and "pdf" in art)
    )


def _is_open_data(obs: dict[str, Any]) -> bool:
    art = obs.get("source_artifact_id") or ""
    oid = obs.get("observation_id") or ""
    return art == "nycha-ddb-open-data-csv" or ":open-data" in oid


def _confidence_ok(obs: dict[str, Any]) -> bool:
    """Low-confidence PDF rows never become current."""
    conf = (obs.get("parser_confidence") or "high").lower()
    return conf in {"high", "medium"}


def resolve_current_tenant_rents(
    *,
    structured_rents: list[dict[str, Any]],
    pdf_rents: list[dict[str, Any]] | None,
    pdf_available: bool,
    pdf_data_as_of: str | None = None,
) -> dict[str, Any]:
    """
    Merge structured + PDF observations into current + historical sets.

    Returns:
      current_rents: one authoritative observation per development_id
      historical_rents: non-current observations retained for query
      selection: per-development resolution metadata
      mixed_vintage: release-level banner stats
    """
    pdf_rents = list(pdf_rents or [])
    # Drop low-confidence PDF rows from the current candidate pool entirely
    # (they remain listed under quarantine by the PDF normalizer).
    pdf_ok = [r for r in pdf_rents if _confidence_ok(r)]
    pdf_rejected = [r for r in pdf_rents if not _confidence_ok(r)]

    by_dev: dict[str, list[dict[str, Any]]] = {}
    for r in structured_rents:
        did = r.get("housing_development_id")
        if not did:
            continue
        by_dev.setdefault(str(did), []).append({**r, "_pool": "structured"})
    for r in pdf_ok:
        did = r.get("housing_development_id")
        if not did:
            continue
        by_dev.setdefault(str(did), []).append({**r, "_pool": "pdf"})

    current: list[dict[str, Any]] = []
    historical: list[dict[str, Any]] = []
    selection: list[dict[str, Any]] = []

    for did, obs_list in sorted(by_dev.items()):
        # Newest period wins; on tie, prefer PDF over structured.
        def sort_key(o: dict[str, Any]) -> tuple:
            d = _period_date(o) or date.min
            pool_rank = 1 if o.get("_pool") == "pdf" else 0
            return (d, pool_rank)

        ranked = sorted(obs_list, key=sort_key, reverse=True)
        winner = ranked[0]
        losers = ranked[1:]

        winner_out = {k: v for k, v in winner.items() if not k.startswith("_")}
        source_kind = "pdf" if winner.get("_pool") == "pdf" else "structured"
        stale = False
        # If PDF failed entirely for this development but a newer PDF vintage
        # is known citywide, flag the structured fallback as stale.
        if source_kind == "structured" and pdf_available and pdf_data_as_of:
            w_date = _period_date(winner)
            try:
                pdf_date = date.fromisoformat(str(pdf_data_as_of)[:10])
            except ValueError:
                pdf_date = None
            if w_date and pdf_date and w_date < pdf_date:
                stale = True
                winner_out = dict(winner_out)
                winner_out["stale_relative_to_pdf"] = True
                winner_out["pdf_data_as_of"] = pdf_data_as_of
                notes = winner_out.get("notes") or ""
                flag = (
                    f" Structured Open Data value retained; newer official PDF "
                    f"vintage {pdf_data_as_of} has no successful parse for this development."
                )
                if flag.strip() not in notes:
                    winner_out["notes"] = (notes + flag).strip()

        current.append(winner_out)
        for loser in losers:
            historical.append({k: v for k, v in loser.items() if not k.startswith("_")})

        selection.append(
            {
                "development_id": did,
                "selected_observation_id": winner_out.get("observation_id"),
                "selected_source": source_kind,
                "selected_period": winner_out.get("period_start"),
                "selected_value": winner_out.get("value"),
                "stale": stale,
                "candidate_count": len(obs_list),
                "historical_observation_ids": [
                    (loser.get("observation_id")) for loser in losers
                ],
            }
        )

    # PDF failed completely → every structured row is current and may be stale
    if not pdf_available and pdf_data_as_of:
        for row in current:
            row["stale_relative_to_pdf"] = True
            row["pdf_data_as_of"] = pdf_data_as_of

    source_counts = Counter(s["selected_source"] for s in selection)
    period_counts = Counter(str(s.get("selected_period") or "unknown") for s in selection)
    stale_count = sum(1 for s in selection if s.get("stale"))
    pdf_advanced = int(source_counts.get("pdf", 0))
    structured_fallback = int(source_counts.get("structured", 0))

    mixed_vintage = {
        "pdf_available": pdf_available,
        "pdf_data_as_of": pdf_data_as_of,
        "developments_current": len(current),
        "advanced_to_pdf": pdf_advanced,
        "retained_structured": structured_fallback,
        "stale_structured_count": stale_count,
        "low_confidence_pdf_rejected": len(pdf_rejected),
        "selected_period_distribution": dict(sorted(period_counts.items())),
        "selected_source_distribution": dict(sorted(source_counts.items())),
        "banner": _banner_text(
            pdf_available=pdf_available,
            pdf_data_as_of=pdf_data_as_of,
            pdf_advanced=pdf_advanced,
            structured_fallback=structured_fallback,
            stale_count=stale_count,
            period_counts=period_counts,
        ),
    }

    return {
        "current_rents": current,
        "historical_rents": historical,
        "selection": selection,
        "mixed_vintage": mixed_vintage,
        "pdf_rejected_low_confidence": pdf_rejected,
    }


def _banner_text(
    *,
    pdf_available: bool,
    pdf_data_as_of: str | None,
    pdf_advanced: int,
    structured_fallback: int,
    stale_count: int,
    period_counts: Counter,
) -> str:
    periods = ", ".join(f"{p}×{n}" for p, n in sorted(period_counts.items()))
    if not pdf_available:
        return (
            f"NYCHA rents from structured Open Data only"
            f"{f'; newer PDF vintage {pdf_data_as_of} not applied' if pdf_data_as_of else ''}"
            f" · periods {periods or 'unknown'}"
        )
    return (
        f"NYCHA current rents: {pdf_advanced} from {pdf_data_as_of or 'PDF'} · "
        f"{structured_fallback} still on structured Open Data"
        f"{f' ({stale_count} stale vs PDF)' if stale_count else ''} · "
        f"periods {periods or 'unknown'}"
    )
