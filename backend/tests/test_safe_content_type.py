"""``safe_content_type`` behaviour (GHSA-h77m-pjqc-5cm3 follow-up).

The 4 evidence/report upload routes now derive the stored MIME from the
filename extension instead of trusting the client's ``Content-Type``
header. SVG is folded down to ``application/octet-stream`` because it
can carry executable content that bypasses
``Content-Disposition: attachment`` in <embed>/<iframe>/<object>
consumers. These tests pin that behaviour.
"""

from __future__ import annotations

import pytest

from utils.uploads import safe_content_type


@pytest.mark.parametrize(
    "filename, expected",
    [
        ("screenshot.png", "image/png"),
        ("Screenshot.PNG", "image/png"),         # case-insensitive suffix
        ("photo.jpg", "image/jpeg"),
        ("photo.jpeg", "image/jpeg"),
        ("animated.gif", "image/gif"),
        ("report.pdf", "application/pdf"),
        ("notes.txt", "text/plain"),
        ("config.json", "application/json"),
        ("page.html", "text/html"),
        ("page.htm", "text/html"),
        ("archive.zip", "application/zip"),
    ],
)
def test_known_safe_extensions_pass_through(filename, expected):
    assert safe_content_type(filename) == expected


@pytest.mark.parametrize(
    "filename",
    [
        "payload.svg",     # SVG can carry inline JS → folded to octet-stream
        "evil.svgz",       # gzip'd SVG, same threat surface
    ],
)
def test_svg_is_neutralised(filename):
    assert safe_content_type(filename) == "application/octet-stream"


@pytest.mark.parametrize(
    "filename",
    [
        "noextension",
        "weird.weirdext",
        "trailingdot.",
        ".hiddenfile",
        "",
        None,
    ],
)
def test_unknown_or_missing_extension_is_octet_stream(filename):
    assert safe_content_type(filename) == "application/octet-stream"


def test_client_content_type_is_irrelevant():
    """The function only inspects the filename. There's no way for a
    caller to pass through a client-supplied header value — that's the
    whole point. This test pins the API shape against any future
    refactor that 'just adds an override parameter for convenience'."""
    import inspect
    sig = inspect.signature(safe_content_type)
    assert list(sig.parameters) == ["filename"], (
        "safe_content_type must accept only `filename`. Adding a "
        "content_type override re-introduces the client-trust gadget "
        "this helper was built to remove (GHSA-h77m-pjqc-5cm3 follow-up)."
    )
