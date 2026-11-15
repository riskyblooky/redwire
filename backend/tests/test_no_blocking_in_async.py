"""CPU- or network-blocking helpers must not run on the event loop from an
async request handler: bcrypt (~100-250 ms), ldap3 binds, SAML signature
checks. Call them through asyncio.to_thread (or the *_async wrappers)."""

from __future__ import annotations

import ast
from pathlib import Path

_BLOCKING = {"verify_password", "get_password_hash", "hash_code", "verify_code",
             "verify_recovery_code", "test_ldap_connection", "authenticate_ldap",
             "authenticate_ldap_with_trace", "process_saml_response"}


def test_async_handlers_do_not_call_blocking_helpers_directly():
    offenders = []
    for path in list(Path("routers").glob("*.py")) + [Path("main.py")]:
        tree = ast.parse(path.read_text())
        for fn in ast.walk(tree):
            if not isinstance(fn, ast.AsyncFunctionDef):
                continue
            # Nested sync defs/lambdas inside the handler run in a thread.
            nested = {id(n) for d in ast.walk(fn) if d is not fn and isinstance(d, (ast.FunctionDef, ast.Lambda))
                      for n in ast.walk(d)}
            for c in ast.walk(fn):
                if isinstance(c, ast.Call) and id(c) not in nested:
                    name = getattr(c.func, "id", getattr(c.func, "attr", None))
                    if name in _BLOCKING:
                        offenders.append(f"{path}:{c.lineno} {fn.name} -> {name}")
    assert offenders == []


async def test_async_wrappers_round_trip():
    from auth.password import get_password_hash_async, verify_password_async
    h = await get_password_hash_async("pw")
    assert await verify_password_async("pw", h) and not await verify_password_async("nope", h)
