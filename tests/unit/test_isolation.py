"""CI isolation checks: fail if peer-product coupling appears."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]

# File extensions / names scanned for coupling markers
SCAN_GLOBS = [
    "**/*.py",
    "**/*.ts",
    "**/*.tsx",
    "**/*.js",
    "**/*.mjs",
    "**/*.json",
    "**/*.yml",
    "**/*.yaml",
    "**/*.toml",
    "**/*.md",
    "**/*.html",
    "**/*.css",
    "Makefile",
]

SKIP_PARTS = {
    ".git",
    ".venv",
    "node_modules",
    "dist",
    "__pycache__",
    ".pytest_cache",
    "uv.lock",
    "package-lock.json",
}


def _deployment_rules() -> dict:
    path = ROOT / "config" / "deployment.yml"
    with path.open(encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)
    return cfg["isolation"]


def _iter_source_files():
    result = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT,
        capture_output=True,
        check=True,
    )
    allowed_suffixes = {
        ".py", ".ts", ".tsx", ".js", ".mjs", ".json", ".yml",
        ".yaml", ".toml", ".md", ".html", ".css",
    }
    for raw_path in result.stdout.decode().split("\0"):
        if not raw_path:
            continue
        path = ROOT / raw_path
        if path.name != "Makefile" and path.suffix not in allowed_suffixes:
            continue
        if any(part in SKIP_PARTS for part in path.parts):
            continue
        # Allow isolation/security policy surfaces to name the markers they forbid
        if path.name == "test_isolation.py":
            continue
        if path.name == "test_edge_hardening.py":
            continue
        if path == ROOT / "config" / "deployment.yml":
            continue
        if path.name == "SECURITY.md":
            continue
        if "security" in path.parts and path.suffix == ".py":
            continue
        if path.name == "README.md":
            continue
        yield path


def test_deployment_identity_is_rent_seekers():
    cfg_path = ROOT / "config" / "deployment.yml"
    text = cfg_path.read_text(encoding="utf-8")
    assert "nyc-rent-seekers" in text
    assert "rent-seekers-deploy" in text
    assert "cityscroll" not in text.lower() or "forbidden" in text.lower()


def test_no_forbidden_package_names_in_repo():
    rules = _deployment_rules()
    forbidden = [n.lower() for n in rules["forbidden_package_names"]]
    offenders: list[str] = []
    for path in _iter_source_files():
        try:
            text = path.read_text(encoding="utf-8", errors="replace").lower()
        except OSError:
            continue
        for name in forbidden:
            if name in text:
                # Allow mentioning in isolation ADR-style docs already skipped
                offenders.append(f"{path.relative_to(ROOT)}: {name}")
    assert offenders == [], "Peer-product coupling markers found:\n" + "\n".join(offenders)


def test_no_forbidden_env_var_prefixes():
    rules = _deployment_rules()
    prefixes = rules["forbidden_env_vars"]
    pattern = re.compile("|".join(re.escape(p) for p in prefixes), re.I)
    offenders: list[str] = []
    for path in _iter_source_files():
        text = path.read_text(encoding="utf-8", errors="replace")
        if pattern.search(text):
            offenders.append(str(path.relative_to(ROOT)))
    assert offenders == [], f"Forbidden env var prefixes found: {offenders}"


def test_no_forbidden_hosts():
    rules = _deployment_rules()
    hosts = [h.lower() for h in rules["forbidden_hosts"]]
    offenders: list[str] = []
    for path in _iter_source_files():
        text = path.read_text(encoding="utf-8", errors="replace").lower()
        for host in hosts:
            if host in text:
                offenders.append(f"{path.relative_to(ROOT)}: {host}")
    assert offenders == [], f"Forbidden hosts found: {offenders}"


def test_package_json_name():
    import json

    pkg = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    assert pkg["name"] == "nyc-rent-seekers"
    assert "cityscroll" not in json.dumps(pkg).lower()


def test_pyproject_package_name():
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'name = "rent-seekers"' in text
    assert "cityscroll" not in text.lower()
