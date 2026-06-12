"""Centralised `max_length` caps for Pydantic string fields.

Why this exists: bounded request bodies are the cheap, broad defence against
the latent DoS surface a few advisories surfaced (GHSA-82jh-8f6p-vgx9 capped
comment bodies; GHSA-8r3m-6x57-pg97 capped pre-auth bodies). This module
extends that discipline to every text field the API accepts so the cap stays
consistent and a single import sites the value in the diff.

Pick the smallest cap that fits the field's real-world use. The goal is a
ceiling that never bites a real user but kills any "send 100 MB at this
endpoint" footgun.
"""

# Identifier / short label shapes -------------------------------------------------
NAME = 255              # display names of resources (engagements, assets, ...)
SHORT_LABEL = 255       # category, type, tag-name, status text
SLUG = 128              # internal slugs, codes, role keys
TITLE = 500             # human titles (findings, runbooks, testcases, ...)

# Network / web shapes -----------------------------------------------------------
URL = 2048              # standard URL ceiling
EMAIL = 254             # RFC 5321 SMTP path limit
HOSTNAME = 255          # RFC 1035
PATH = 4096             # file paths
IP_ADDR = 45            # IPv6 max
HEX_COLOR = 7           # "#rrggbb"

# Crypto / token shapes ----------------------------------------------------------
TOKEN = 4096            # JWT / refresh / api-token
SHORT_TOKEN = 128       # signed code, registration code, reset code
HASH = 128              # hex digest
UUID_FIELD = 64         # UUID PKs and FKs (36 chars + headroom)

# Free-form text shapes ----------------------------------------------------------
NOTE = 16384            # ~16 KB — short notes / single-paragraph fields
DESCRIPTION = 32768     # ~32 KB — finding / testcase descriptions, comments
LONG_TEXT = 65536       # ~64 KB — large prose blocks (mitigations, full reports)

# Structured / generated shapes --------------------------------------------------
CVSS_VECTOR = 100       # CVSS v3 / v4 vector strings cap out around ~80
ENUM_STR = 32           # string-typed enum values
JSON_BLOB = 1_048_576   # 1 MiB — settings JSON dumped to text

__all__ = [
    "NAME", "SHORT_LABEL", "SLUG", "TITLE",
    "URL", "EMAIL", "HOSTNAME", "PATH", "IP_ADDR", "HEX_COLOR",
    "TOKEN", "SHORT_TOKEN", "HASH", "UUID_FIELD",
    "NOTE", "DESCRIPTION", "LONG_TEXT",
    "CVSS_VECTOR", "ENUM_STR", "JSON_BLOB",
]
