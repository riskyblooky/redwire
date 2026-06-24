"""Single source of truth for the running platform version.

Read by both ``main.py`` (FastAPI app version banner) and the plugin
loader (``min_redwire_version`` enforcement). Bumping this here is
the only change needed when cutting a new release.
"""

VERSION = "1.0.0"


def _to_tuple(v: str) -> tuple[int, ...]:
    """Parse "1.2.3" → (1, 2, 3) for comparison. Non-integer
    components are treated as 0 so weird tags (`1.2.3-rc1`) compare
    as `1.2.3` rather than crashing."""
    parts: list[int] = []
    for chunk in (v or "0").split("."):
        try:
            parts.append(int(chunk))
        except (ValueError, TypeError):
            parts.append(0)
    return tuple(parts)


def version_meets(required: str, current: str = VERSION) -> bool:
    """True if ``current`` >= ``required`` under semver-ish ordering.

    Used by the plugin loader to gate ``min_redwire_version``. A
    plugin authored against 1.5.0 refuses to load on a 1.4.0
    backend.
    """
    return _to_tuple(current) >= _to_tuple(required)
