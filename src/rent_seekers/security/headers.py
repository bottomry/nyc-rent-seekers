"""CSP and static-edge security headers (NRS-012 / §12.2 + §12.4)."""

from __future__ import annotations

from typing import Any

from rent_seekers.config import deployment_config

# Production multi-file app: scripts/styles/assets same-origin only.
# MapLibre may use blob: workers and data: images; styles can be injected.
DEFAULT_CSP = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: blob:; "
    "font-src 'self' data:; "
    "connect-src 'self'; "
    "worker-src 'self' blob:; "
    "child-src 'self' blob:; "
    "object-src 'none'; "
    "base-uri 'self'; "
    "form-action 'none'; "
    "frame-ancestors 'none'"
)

DEFAULT_SECURITY_HEADERS: dict[str, str] = {
    "Content-Security-Policy": DEFAULT_CSP,
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": (
        "accelerometer=(), camera=(), geolocation=(), gyroscope=(), "
        "magnetometer=(), microphone=(), payment=(), usb=()"
    ),
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
    "X-Permitted-Cross-Domain-Policies": "none",
}


def security_policy() -> dict[str, Any]:
    """Merged security policy from config/deployment.yml + defaults."""
    cfg = deployment_config()
    sec = cfg.get("security") or {}
    if not isinstance(sec, dict):
        sec = {}
    headers = dict(DEFAULT_SECURITY_HEADERS)
    custom = sec.get("headers") or {}
    if isinstance(custom, dict):
        for k, v in custom.items():
            if v is None:
                headers.pop(str(k), None)
            else:
                headers[str(k)] = str(v)
    csp = sec.get("content_security_policy")
    if isinstance(csp, str) and csp.strip():
        headers["Content-Security-Policy"] = csp.strip()
    return {
        "headers": headers,
        "content_security_policy": headers.get("Content-Security-Policy", DEFAULT_CSP),
        "frame_ancestors": "none",
        "cookies": "none",
        "third_party_analytics": False,
        "provider_tokens_in_browser": False,
        "basemap": sec.get("basemap") or "local-nyc-geojson",
        "origin_isolation": sec.get("origin_isolation")
        or "separate-static-origin-from-cairn-cityscroll",
    }


def security_header_map() -> dict[str, str]:
    return dict(security_policy()["headers"])


def format_netlify_header_block(path_pattern: str, headers: dict[str, str]) -> str:
    lines = [path_pattern]
    for name, value in headers.items():
        lines.append(f"  {name}: {value}")
    return "\n".join(lines)


def build_headers_file(
    *,
    scope: str,
    cache_control: dict[str, str],
    release_id: str | None = None,
) -> str:
    """
    Netlify/Cloudflare-style _headers body for a release tree or dist root.

    scope:
      - "release" — paths relative to /releases/<id>/ or /app/
      - "root" — dist root pointer/status + releases/*
    """
    sec = security_header_map()
    immutable = cache_control.get(
        "immutable_assets", "public, max-age=31536000, immutable"
    )
    pointer = cache_control.get(
        "pointer_and_status", "public, max-age=60, must-revalidate"
    )
    html = cache_control.get("html_entry", "public, max-age=300, must-revalidate")

    blocks: list[str] = []
    if scope == "release":
        rid = release_id or "release"
        blocks.append(f"# Static-edge security + cache policy (NRS-012 / §12) — {rid}")
        # Apply security headers to all paths under this tree
        blocks.append(format_netlify_header_block("/*", sec))
        blocks.append(
            "\n".join(
                [
                    "/assets/*",
                    f"  Cache-Control: {immutable}",
                    "/data/*",
                    f"  Cache-Control: {immutable}",
                    "/index.html",
                    f"  Cache-Control: {html}",
                    "/manifest.json",
                    f"  Cache-Control: {immutable}",
                    "/status.json",
                    f"  Cache-Control: {pointer}",
                    "/cache-control.json",
                    f"  Cache-Control: {pointer}",
                    "/security-headers.json",
                    f"  Cache-Control: {pointer}",
                ]
            )
        )
    else:
        blocks.append("# Root pointer / status / release cache + security (NRS-012 / §12)")
        blocks.append(format_netlify_header_block("/*", sec))
        blocks.append(
            "\n".join(
                [
                    "/latest.json",
                    f"  Cache-Control: {pointer}",
                    "/status.json",
                    f"  Cache-Control: {pointer}",
                    "/releases/*",
                    f"  Cache-Control: {immutable}",
                    "/app/*",
                    f"  Cache-Control: {html}",
                ]
            )
        )
    return "\n".join(blocks) + "\n"


def security_headers_document() -> dict[str, Any]:
    """Machine-readable policy shipped with each release for operators/gates."""
    pol = security_policy()
    return {
        "project": "nyc-rent-seekers",
        "card": "NRS-012",
        "static_edge": True,
        "read_only": True,
        "cookies": "none",
        "server_side_search": False,
        "dynamic_calculation_endpoint": False,
        "ingestion_from_browser": False,
        "database": False,
        "shared_credentials_with_peers": False,
        "provider_tokens_in_browser": False,
        "basemap": pol.get("basemap"),
        "origin_isolation": pol.get("origin_isolation"),
        "headers": pol["headers"],
        "content_security_policy": pol["content_security_policy"],
    }
