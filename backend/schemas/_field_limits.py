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

# Collection / list shapes --------------------------------------------------------
# GHSA-7x2f-ff7r-h388 #9, #10, #13 (CWE-770): global caps for list endpoints and
# unbounded object payloads. Sized generously so no legitimate UI query bites
# the cap while still killing "SELECT 100_000 findings" and "attach a dict with
# a million node positions" DoS shapes at the schema boundary. Pick the
# smallest cap that fits real use — the goal is a ceiling that never bites a
# real workflow but neutralises the resource-consumption footgun.
MAX_LIST_LIMIT = 500    # `limit=` on list endpoints
MAX_RUNBOOK_ITEMS = 500 # items[] on a runbook create/update
MAX_GRAPH_NODES = 5000  # nodes in an attack-graph positions dict

__all__ = [
    "NAME", "SHORT_LABEL", "SLUG", "TITLE",
    "URL", "EMAIL", "HOSTNAME", "PATH", "IP_ADDR", "HEX_COLOR",
    "TOKEN", "SHORT_TOKEN", "HASH", "UUID_FIELD",
    "NOTE", "DESCRIPTION", "LONG_TEXT",
    "CVSS_VECTOR", "ENUM_STR", "JSON_BLOB",
    "MAX_LIST_LIMIT", "MAX_RUNBOOK_ITEMS", "MAX_GRAPH_NODES",
]
