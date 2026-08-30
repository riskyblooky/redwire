# Third-party components

Everything under this directory is **third-party code/content that is NOT
covered by RedWire's Apache-2.0 license**. Each subdirectory is a separate
upstream project, kept verbatim, with its own `LICENSE` file and a
`PROVENANCE.md` recording where it came from.

The boundary is deliberate: RedWire's own source (Apache-2.0) never copies
text out of these files into its own modules. Code that uses this content
(e.g. `backend/utils/writing_skills.py`) loads it from disk at runtime by
path — it does not embed it.

| Directory | Upstream | License |
|---|---|---|
| `yeswehack-claude-kit/` | https://github.com/yeswehack/claude-kit | GPL-3.0-only |

See `../../THIRD_PARTY_LICENSES.md` (repo root) for the consolidated record.

> **Note on GPL-3.0:** these files are GPL-licensed and remain so. They are
> kept isolated here and used as data (loaded at runtime), not linked into
> RedWire's Apache-2.0 code. If you redistribute RedWire, keep this directory,
> its `LICENSE`, and the provenance intact.
