"""Load project configuration."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]


def project_root() -> Path:
    return ROOT


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError(f"expected mapping in {path}")
    return data


def deployment_config() -> dict[str, Any]:
    return load_yaml(ROOT / "config" / "deployment.yml")


def sources_config() -> dict[str, Any]:
    return load_yaml(ROOT / "config" / "sources.yml")


def comparison_policy() -> dict[str, Any]:
    return load_yaml(ROOT / "config" / "comparison_policy.yml")
