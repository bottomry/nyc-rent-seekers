"""The public-bound product graph cannot absorb maintainer-only documents."""

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PRIVATE_PATHS = {
    "docs/adr",
    "docs/adr/**",
    "docs/THREAT_MODEL.md",
    "docs/spec.md",
    "docs/PROGRESS.md",
    "product",
    "product/**",
    ".private-product",
    ".private-product/**",
}


def test_private_path_manifest_is_complete():
    entries = {
        line.strip()
        for line in (ROOT / ".scrim-private").read_text().splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    assert entries == PRIVATE_PATHS


def test_private_overlay_paths_are_gitignored():
    concrete = sorted(path for path in PRIVATE_PATHS if "*" not in path)
    proc = subprocess.run(
        ["git", "check-ignore", "--stdin"],
        cwd=ROOT,
        input="\n".join(concrete) + "\n",
        text=True,
        capture_output=True,
        check=False,
    )
    assert proc.returncode == 0
    assert set(proc.stdout.splitlines()) == set(concrete)


def test_private_overlay_installer_is_valid_shell():
    installer = ROOT / "scripts/install-private-docs.sh"
    subprocess.run(
        ["/bin/sh", "-n", str(installer)],
        check=True,
    )
    source = installer.read_text()
    assert "ln -s ../../nyc-rent-seekers-internal" not in source
    assert 'ln -s "$companion_link/' in source
