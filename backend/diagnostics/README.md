# Diagnostics

One-off, hand-run verification scripts (not part of the pytest suite). They
`print()` rather than assert, and exist to debug specific past incidents
(password hashing). Run directly inside the backend container:

```bash
docker compose exec backend python diagnostics/check_hash.py
```

Real tests live in `../tests/` and run via `pytest`.
