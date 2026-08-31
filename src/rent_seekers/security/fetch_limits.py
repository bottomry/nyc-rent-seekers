"""Build-time source-fetch limits: host allowlist, size, timeout (§12.5 / NRS-012)."""

from __future__ import annotations

import re
import time
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlparse

from rent_seekers.config import deployment_config, sources_config

# Hard defaults when config omits values
DEFAULT_TIMEOUT_S = 60
DEFAULT_MAX_BYTES = 80 * 1024 * 1024  # 80 MiB
DEFAULT_MAX_RETRIES = 2
DEFAULT_BACKOFF_S = 1.5

# Hosts that may appear in sources.yml / fixtures (build-time only)
BUILTIN_ALLOWED_HOST_SUFFIXES = (
    "data.cityofnewyork.us",
    "nyc.gov",
    "www.nyc.gov",
    "huduser.gov",
    "www.huduser.gov",
    "zillow.com",
    "www.zillow.com",
    "files.zillowstatic.com",
    "zillowstatic.com",
)


class FetchLimitError(RuntimeError):
    """Raised when a fetch violates operational limits or host policy."""


def fetch_limits() -> dict[str, Any]:
    cfg = deployment_config()
    limits = cfg.get("source_fetch") or cfg.get("operational_limits") or {}
    if not isinstance(limits, dict):
        limits = {}
    sf = limits.get("source_fetch") if "source_fetch" in limits else limits
    if not isinstance(sf, dict):
        sf = {}
    # Prefer nested security/operational_limits.source_fetch
    op = cfg.get("operational_limits") or {}
    if isinstance(op, dict) and isinstance(op.get("source_fetch"), dict):
        merged = dict(sf)
        merged.update(op["source_fetch"])
        sf = merged
    return {
        "timeout_seconds": int(sf.get("timeout_seconds") or DEFAULT_TIMEOUT_S),
        "max_download_bytes": int(sf.get("max_download_bytes") or DEFAULT_MAX_BYTES),
        "max_retries": int(
            sf.get("max_retries")
            if sf.get("max_retries") is not None
            else DEFAULT_MAX_RETRIES
        ),
        "backoff_seconds": float(sf.get("backoff_seconds") or DEFAULT_BACKOFF_S),
        "user_agent": sf.get("user_agent")
        or (
            "Mozilla/5.0 (compatible; nyc-rent-seekers/0.1; "
            "+https://github.com/bottomry/nyc-rent-seekers)"
        ),
    }


def _hosts_from_sources_config() -> set[str]:
    hosts: set[str] = set()
    try:
        raw = sources_config()
    except (OSError, ValueError):
        return hosts
    sources = raw.get("sources") or {}
    if not isinstance(sources, dict):
        return hosts
    url_keys = (
        "current_url",
        "csv_url",
        "geojson_url",
        "bulk_url",
        "bulk_url_original",
        "landing_page",
        "fmr_page",
        "methodology_url",
    )
    for _name, entry in sources.items():
        if not isinstance(entry, dict):
            continue
        for key in url_keys:
            url = entry.get(key)
            if isinstance(url, str) and url.startswith("http"):
                host = urlparse(url).hostname
                if host:
                    hosts.add(host.lower())
    return hosts


def allowed_source_hosts() -> frozenset[str]:
    """Allowlisted hosts for build-time HTTP retrieval only."""
    cfg = deployment_config()
    op = cfg.get("operational_limits") or {}
    sf = op.get("source_fetch") if isinstance(op, dict) else {}
    if not isinstance(sf, dict):
        sf = {}
    extra = sf.get("allowed_hosts") or []
    hosts: set[str] = {h.lower() for h in BUILTIN_ALLOWED_HOST_SUFFIXES}
    hosts |= _hosts_from_sources_config()
    if isinstance(extra, list):
        for h in extra:
            if isinstance(h, str) and h.strip():
                hosts.add(h.strip().lower())
    return frozenset(hosts)


def host_is_allowed(hostname: str | None, allowed: frozenset[str] | None = None) -> bool:
    if not hostname:
        return False
    host = hostname.lower().rstrip(".")
    allow = allowed if allowed is not None else allowed_source_hosts()
    if host in allow:
        return True
    # Suffix match: sub.nyc.gov matches nyc.gov allowlist entry
    for entry in allow:
        if host == entry or host.endswith("." + entry):
            return True
    return False


def assert_url_allowed(url: str, *, allowed: frozenset[str] | None = None) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise FetchLimitError(f"refusing non-http(s) URL scheme: {parsed.scheme!r}")
    host = parsed.hostname
    if not host_is_allowed(host, allowed):
        raise FetchLimitError(
            f"source host not allowlisted: {host!r} (url={url!r})"
        )
    return host or ""


def _read_with_limit(resp: Any, max_bytes: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    # Prefer Content-Length when present
    cl = resp.headers.get("Content-Length")
    if cl is not None:
        try:
            if int(cl) > max_bytes:
                raise FetchLimitError(
                    f"Content-Length {cl} exceeds max_download_bytes {max_bytes}"
                )
        except ValueError:
            pass
    while True:
        chunk = resp.read(1024 * 256)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise FetchLimitError(
                f"download exceeded max_download_bytes {max_bytes} (got ≥{total})"
            )
        chunks.append(chunk)
    return b"".join(chunks)


def safe_fetch_url(
    url: str,
    *,
    timeout: int | None = None,
    max_bytes: int | None = None,
    user_agent: str | None = None,
    max_retries: int | None = None,
    backoff_seconds: float | None = None,
    allowed_hosts: frozenset[str] | None = None,
) -> bytes:
    """
    HTTP GET with host allowlist, timeout, max size, and limited retries.

    Build-time only. Never used by the browser or static edge.
    """
    limits = fetch_limits()
    timeout_s = int(timeout if timeout is not None else limits["timeout_seconds"])
    max_b = int(max_bytes if max_bytes is not None else limits["max_download_bytes"])
    retries = int(max_retries if max_retries is not None else limits["max_retries"])
    backoff = float(
        backoff_seconds if backoff_seconds is not None else limits["backoff_seconds"]
    )
    ua = user_agent or limits["user_agent"]

    assert_url_allowed(url, allowed=allowed_hosts)

    last_err: Exception | None = None
    attempts = max(1, retries + 1)
    for attempt in range(attempts):
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": ua,
                    "Accept": "*/*",
                },
                method="GET",
            )
            with urllib.request.urlopen(req, timeout=timeout_s) as resp:
                data = _read_with_limit(resp, max_b)
                if not data:
                    raise RuntimeError(
                        f"empty response body from {url} "
                        f"(HTTP {getattr(resp, 'status', '?')}; content-type="
                        f"{resp.headers.get('Content-Type')!r})"
                    )
                return data
        except FetchLimitError:
            raise
        except (urllib.error.URLError, TimeoutError, OSError, RuntimeError) as exc:
            last_err = exc
            if attempt + 1 >= attempts:
                break
            time.sleep(backoff * (attempt + 1))
    raise RuntimeError(f"fetch failed after {attempts} attempt(s) for {url}: {last_err}")


# Patterns that must never appear as live browser fetch targets in release JS/HTML
FORBIDDEN_RUNTIME_HOST_RE = re.compile(
    r"https?://("
    r"data\.cityofnewyork\.us|"
    r"(?:www\.)?huduser\.gov|"
    r"files\.zillowstatic\.com|"
    r"(?:www\.)?zillow\.com/research|"
    r"(?:www\.)?nyc\.gov/assets/nycha"
    r")",
    re.I,
)
