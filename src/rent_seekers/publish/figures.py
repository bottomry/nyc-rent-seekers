"""Publish content-addressed rental evidence for permanent figure URLs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rent_seekers.sources.base import sha256_bytes


def figure_document(root: Path) -> dict[str, Any]:
    def read(name: str):
        return json.loads((root / name).read_text())

    evidence = read("nychvs/estimates.json")
    return {
        "schema_version": 1,
        "evidence": {
            key: evidence[key]
            for key in (
                "survey_vintage",
                "source_artifacts",
                "protection_estimates",
                "space_estimates",
            )
        },
        "geometry": read("geometry/ntas.geojson"),
        "freeze": read("rent-freeze/boroughs.json"),
        "allocation": read("allocation/reference.json"),
        "method": read("methods/rental-figures.json"),
    }


def publish_figure(root: Path) -> str:
    document = figure_document(root)
    for artifact in document["evidence"]["source_artifacts"].values():
        if len(artifact["sha256"]) != 64:
            raise ValueError("missing source checksum")
    payload = (
        json.dumps(
            document, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        )
        + "\n"
    ).encode()
    digest = sha256_bytes(payload)
    folder = root / "figures"
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"{digest}.json"
    if target.exists():
        if target.read_bytes() != payload:
            raise ValueError("immutable figure content differs")
    else:
        with target.open("xb") as file:
            file.write(payload)
    (folder / "current.json").write_text(
        json.dumps({"schema_version": 1, "figure_id": digest}) + "\n"
    )
    return digest


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("data", type=Path)
    print(publish_figure(parser.parse_args().data))
