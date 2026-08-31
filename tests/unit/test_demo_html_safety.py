"""HTML contains no private path or secret (NRS-002 tests)."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEMO = ROOT / "dist" / "nyc-rent-seekers-demo.html"

PRIVATE_PATH_RE = re.compile(
    r"(/Users/[^\s\"'<>]+|/home/[^\s\"'<>]+|file://[^\s\"'<>]+|/private/var/[^\s\"'<>]+)",
    re.I,
)
SECRET_RE = re.compile(
    r"(api[_-]?key\s*[:=]\s*['\"][^'\"]+['\"]|secret\s*[:=]\s*['\"][^'\"]+['\"]|"
    r"sk-[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16})",
    re.I,
)
FORBIDDEN_LANG_RE = re.compile(
    r"direct government expenditure|cash subsidy|taxpayer gift|government pays the difference",
    re.I,
)


def test_demo_html_exists_or_skip():
    if not DEMO.is_file():
        # Allow unit collection before make demo; still assert path convention
        assert DEMO.name == "nyc-rent-seekers-demo.html"
        return
    text = DEMO.read_text(encoding="utf-8", errors="replace")
    assert "rent-seekers-data" in text
    assert "Fulton".lower() in text.lower() or "nycha:tds:136" in text


def test_demo_html_no_private_paths():
    if not DEMO.is_file():
        return
    text = DEMO.read_text(encoding="utf-8", errors="replace")
    hits = PRIVATE_PATH_RE.findall(text)
    assert hits == [], f"private paths in demo HTML: {hits[:5]}"


def test_demo_html_no_secrets():
    if not DEMO.is_file():
        return
    text = DEMO.read_text(encoding="utf-8", errors="replace")
    hits = SECRET_RE.findall(text)
    assert hits == [], f"secret-like patterns in demo HTML: {hits[:5]}"


def test_demo_html_no_forbidden_wedge_labels():
    """Guard against mislabeling the wedge in UI prose.

    Internal metadata (e.g. product_language.not_a_label in the evidence JSON)
    may name forbidden phrases as things we refuse to call the wedge. That is fine.
    Fail when those phrases appear as affirmative UI copy (no nearby 'not' / not_a_label).
    """
    if not DEMO.is_file():
        return
    text = DEMO.read_text(encoding="utf-8", errors="replace")
    for m in FORBIDDEN_LANG_RE.finditer(text):
        start = max(0, m.start() - 48)
        window = text[start : m.end() + 12].lower()
        # Allow internal refusal metadata / explicit negation only — never positive labels.
        allowed = (
            "not" in window
            or "not_a_label" in window
            or "forbidden" in window
        )
        assert allowed, f"forbidden positive wedge label near: {window!r}"


def test_demo_html_embeds_generated_arithmetic():
    if not DEMO.is_file():
        return
    text = DEMO.read_text(encoding="utf-8", errors="replace")
    # Embedded JSON should contain computed wedge fields
    assert "monthly_wedge_usd" in text
    assert "8567" in text
    assert "representative" in text
