"""Filesystem path safety helpers."""
import os


def ensure_within(path: str, root: str) -> bool:
    """Return True if ``path`` resolves inside ``root``.

    Both arguments are resolved with ``realpath`` so symlinks, ``..`` segments,
    and relative components cannot smuggle the result outside ``root``. The
    comparison appends ``os.sep`` to the resolved root so ``/var/uploads_x``
    does not satisfy a check against ``/var/uploads``.

    Use this before any ``os.remove`` / ``open(..., 'wb')`` / ``shutil`` call
    whose target could be (or could become) influenced by stored or external
    state. Callers decide how to react on a False return — usually log and
    skip, not raise, so a single corrupted record cannot brick an endpoint.
    """
    if not path or not root:
        return False
    try:
        resolved_path = os.path.realpath(path)
        resolved_root = os.path.realpath(root)
    except OSError:
        return False
    return resolved_path.startswith(resolved_root + os.sep)
