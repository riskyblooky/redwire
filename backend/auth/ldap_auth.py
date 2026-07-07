"""
LDAP authentication module.
Uses ldap3 to bind and search against an LDAP/Active Directory server.
"""
from typing import Optional, Dict, Any, List
import logging
import tempfile
import os
import time

logger = logging.getLogger(__name__)


# Bound both the TCP connect and each subsequent read on the LDAP socket so
# a silent server (dropped packets after handshake, half-open connection,
# firewall black-hole) can't wedge a login request forever. Applied to the
# service bind, user search, AND the user-verify bind — the second half
# of two-stage auth used to be unbounded too.
#
# Override at deploy time with ``LDAP_LOGIN_TIMEOUT_S`` in the .env; default
# is a middle-ground 15s. Tune down for local/fast networks, up for
# geographically-distant DCs. ``test_ldap_connection`` keeps its own hard
# 10s cap independent of this so a wedged "Test Connection" click can't
# stall the admin UI.
_DEFAULT_LOGIN_TIMEOUT_S = 15


def _login_timeout_s() -> int:
    """Read the operator-tunable login timeout, clamped to a sane range."""
    raw = os.environ.get("LDAP_LOGIN_TIMEOUT_S", "").strip()
    if not raw:
        return _DEFAULT_LOGIN_TIMEOUT_S
    try:
        v = int(raw)
    except ValueError:
        logger.warning(
            "Invalid LDAP_LOGIN_TIMEOUT_S=%r; falling back to %d",
            raw, _DEFAULT_LOGIN_TIMEOUT_S,
        )
        return _DEFAULT_LOGIN_TIMEOUT_S
    # Clamp so an operator can't misconfigure themselves into a
    # never-timeout or 0-second-timeout state.
    return max(3, min(v, 120))


# ── Debug tracing ──────────────────────────────────────────────────────
#
# When the admin toggles ``ldap_debug_enabled`` on, the auth path (and
# the /test endpoint) build a step-by-step ``trace`` list — one entry per
# meaningful action (resolve TLS, open server, bind service account,
# search user, bind user). Passwords are never included in trace entries;
# bind DNs and search filters are surfaced verbatim so misconfigured
# search bases or filter templates are obvious.
#
# The trace is returned from ``test_ldap_connection`` and logged (at INFO)
# from ``authenticate_ldap`` so operators debugging a real login attempt
# can grep ``[LDAP DEBUG]`` in the container logs.


def _now_ms() -> float:
    return time.monotonic() * 1000.0


def _trace_step(trace: Optional[List[Dict[str, Any]]], step: str, ok: bool,
                message: str, started_ms: Optional[float] = None) -> None:
    """Append a trace step if ``trace`` is not None (i.e. debug is on)."""
    if trace is None:
        return
    entry: Dict[str, Any] = {"step": step, "ok": ok, "message": message}
    if started_ms is not None:
        entry["elapsed_ms"] = round(_now_ms() - started_ms, 2)
    trace.append(entry)


def _escape_ldap_filter(value: str) -> str:
    """Escape special characters for LDAP search filters (RFC 4515).

    Prevents LDAP filter injection by hex-encoding characters that have
    special meaning inside an LDAP search filter expression.
    """
    replacements = {
        "\\": "\\5c",  # must be first
        "*": "\\2a",
        "(": "\\28",
        ")": "\\29",
        "\x00": "\\00",
    }
    for char, escaped in replacements.items():
        value = value.replace(char, escaped)
    return value


def _resolve_tls_mode(settings: Dict[str, str]) -> str:
    """Return one of ``none`` / ``ldaps`` / ``starttls``.

    Reads the new ``tls_mode`` first. Falls back to the legacy
    ``tls_enabled`` bool for installs that haven't re-saved settings
    since the migration — true → ``ldaps``, false → ``none``. That's
    the safest interpretation given the old bool never actually invoked
    StartTLS anyway; installs that were relying on ``true`` + ``ldap://``
    were plaintext in practice, so mapping them to ``ldaps`` at least
    fails loudly if the port is wrong instead of silently leaking.
    """
    mode = (settings.get("tls_mode") or "").strip().lower()
    if mode in ("none", "ldaps", "starttls"):
        return mode
    legacy = settings.get("tls_enabled")
    if legacy is None:
        return "ldaps"
    return "ldaps" if str(legacy).lower() == "true" else "none"


def _build_tls_config(settings: Dict[str, str]):
    """Build an ldap3 Tls object from settings.

    Uses CERT_REQUIRED when a CA cert is provided or by default.
    Falls back to CERT_NONE when ``tls_verify`` is explicitly ``'false'``.
    """
    try:
        from ldap3 import Tls
        import ssl
    except ImportError:
        return None

    ca_cert_pem = settings.get("tls_ca_cert", "").strip()
    tls_verify = str(settings.get("tls_verify", "true")).lower() != "false"

    if not tls_verify:
        logger.warning("LDAP TLS certificate validation is DISABLED (tls_verify=false)")
        return Tls(validate=ssl.CERT_NONE)

    if ca_cert_pem:
        # Write CA cert to temp file for ssl context
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pem", mode="w")
        tmp.write(ca_cert_pem)
        tmp.close()
        return Tls(validate=ssl.CERT_REQUIRED, ca_certs_file=tmp.name)

    return Tls(validate=ssl.CERT_REQUIRED)


def _open_server_and_connection(
    settings: Dict[str, str],
    user: Optional[str],
    password: Optional[str],
    *,
    connect_timeout: Optional[int] = None,
    receive_timeout: Optional[int] = None,
    trace: Optional[List[Dict[str, Any]]] = None,
    bind_label: str = "bind",
):
    """Open a Server + Connection with the correct TLS mode.

    Handles all three modes uniformly so ``authenticate_ldap`` and
    ``test_ldap_connection`` can't drift from each other:
      * ``none``     — plain LDAP; no TLS config, no start_tls().
      * ``ldaps``    — TLS from connect. TLS config attached to Server;
                       ldap3 negotiates TLS on the wire immediately when
                       the URL is ``ldaps://``.
      * ``starttls`` — plain connect, then Connection.start_tls() before
                       any bind or search. auto_bind is deliberately off
                       here — we need to insert start_tls() between the
                       socket connect and the bind so credentials don't
                       cross the wire in the clear. Caller is expected
                       to invoke ``.bind()`` after this returns.

    Returns ``(server, connection)``. Connection is always unbound and
    the caller must ``.bind()`` (or ``.rebind()`` for the second step of
    two-stage auth). For ``ldaps`` and ``none`` we still let auto_bind
    do its thing when caller passes it, but the shared path here does
    the connect + optional start_tls only.
    """
    from ldap3 import Server, Connection, ALL

    mode = _resolve_tls_mode(settings)
    server_url = settings["server_url"]

    _trace_step(
        trace, "resolve_tls_mode", True,
        f"tls_mode={mode}, tls_verify={str(settings.get('tls_verify', 'true')).lower()!r}"
        f", server_url={server_url!r}",
    )

    server_kwargs: Dict[str, Any] = {"get_info": ALL}
    if connect_timeout is not None:
        server_kwargs["connect_timeout"] = connect_timeout

    if mode in ("ldaps", "starttls"):
        server_kwargs["tls"] = _build_tls_config(settings)

    server = Server(server_url, **server_kwargs)

    # For starttls: connect + upgrade BEFORE binding, so the bind
    # password isn't leaked over plaintext.
    # receive_timeout bounds every read operation on the connection
    # (bind response, search response). Combined with the server's
    # connect_timeout, this makes every step of the handshake wall-time
    # bounded — a silent server can't hang a login request.
    conn_kwargs: Dict[str, Any] = {"user": user, "password": password}
    if receive_timeout is not None:
        conn_kwargs["receive_timeout"] = receive_timeout

    if mode == "starttls":
        t0 = _now_ms()
        conn = Connection(server, auto_bind=False, **conn_kwargs)
        if not conn.open():
            _trace_step(trace, "open_socket", False, f"failed: {conn.result}", t0)
            raise RuntimeError(f"LDAP connect failed: {conn.result}")
        _trace_step(trace, "open_socket", True, f"plain socket to {server_url}", t0)

        t1 = _now_ms()
        if not conn.start_tls():
            _trace_step(trace, "starttls", False, f"failed: {conn.result}", t1)
            raise RuntimeError(f"LDAP StartTLS failed: {conn.result}")
        _trace_step(trace, "starttls", True, "TLS upgrade OK", t1)

        t2 = _now_ms()
        if not conn.bind():
            _trace_step(trace, bind_label, False,
                        f"user={user!r} result={conn.result}", t2)
            raise RuntimeError(f"LDAP bind failed: {conn.result}")
        _trace_step(trace, bind_label, True, f"user={user!r}", t2)
        return server, conn

    # ldaps or plain: single-step auto_bind is fine.
    t0 = _now_ms()
    try:
        conn = Connection(server, auto_bind=True, **conn_kwargs)
    except Exception as exc:
        _trace_step(trace, bind_label, False,
                    f"user={user!r} error={exc.__class__.__name__}: {exc}", t0)
        raise
    _trace_step(trace, bind_label, True,
                f"user={user!r} ({'ldaps' if mode == 'ldaps' else 'plain'})", t0)
    return server, conn


def authenticate_ldap(
    username: str,
    password: str,
    settings: Dict[str, str],
    *,
    debug: bool = False,
) -> Optional[Dict[str, Any]]:
    """
    Authenticate a user against LDAP.

    Returns a dict with user info (username, email, full_name) on success,
    or None on failure.

    When ``debug`` is True, a per-step trace is emitted at INFO with the
    ``[LDAP DEBUG]`` prefix so operators can reconstruct what happened
    (which step failed, how long each took, what search filter actually
    hit the server). The trace never contains passwords.
    """
    trace: Optional[List[Dict[str, Any]]] = [] if debug else None
    try:
        from ldap3 import SUBTREE
    except ImportError:
        logger.error("ldap3 package not installed")
        _trace_step(trace, "import_ldap3", False, "ldap3 package missing")
        _emit_trace(trace, username, ok=False)
        return None

    server_url = settings.get("server_url", "")
    bind_dn = settings.get("bind_dn", "")
    bind_password = settings.get("bind_password", "")
    search_base = settings.get("search_base", "")
    search_filter = settings.get("search_filter", "(uid={username})")
    username_attr = settings.get("username_attribute", "uid")
    email_attr = settings.get("email_attribute", "mail")
    fullname_attr = settings.get("fullname_attribute", "cn")

    if not server_url or not search_base:
        logger.error("LDAP server_url or search_base not configured")
        _trace_step(trace, "validate_settings", False,
                    f"server_url={server_url!r} search_base={search_base!r}")
        _emit_trace(trace, username, ok=False)
        return None
    _trace_step(trace, "validate_settings", True,
                f"search_base={search_base!r}, filter_template={search_filter!r}, "
                f"username_attr={username_attr!r}")

    # Wall-clock cap on every socket op (connect + read). Applied to both
    # binds and the intervening search so a wedged DC can't stall a login
    # request. Configurable via LDAP_LOGIN_TIMEOUT_S in the environment.
    timeout_s = _login_timeout_s()
    _trace_step(trace, "resolve_timeout", True,
                f"login_timeout_s={timeout_s} (env: LDAP_LOGIN_TIMEOUT_S)")

    try:
        # Step 1: Bind with service account to search for user DN
        server, search_conn = _open_server_and_connection(
            settings, user=bind_dn, password=bind_password,
            connect_timeout=timeout_s, receive_timeout=timeout_s,
            trace=trace, bind_label="bind_service",
        )

        # Escape username to prevent LDAP filter injection, then substitute
        safe_username = _escape_ldap_filter(username)
        actual_filter = search_filter.replace("{username}", safe_username)
        t = _now_ms()
        search_conn.search(
            search_base=search_base,
            search_filter=actual_filter,
            search_scope=SUBTREE,
            attributes=[username_attr, email_attr, fullname_attr],
        )
        _trace_step(trace, "search_user",
                    len(search_conn.entries) > 0,
                    f"filter={actual_filter!r} → {len(search_conn.entries)} entrie(s)", t)

        if not search_conn.entries:
            logger.info(f"LDAP user not found: {username}")
            search_conn.unbind()
            _emit_trace(trace, username, ok=False)
            return None

        user_entry = search_conn.entries[0]
        user_dn = str(user_entry.entry_dn)
        search_conn.unbind()

        # Step 2: Bind as the user to verify password. Reopen with the
        # same TLS mode so the user bind is protected the same way as
        # the service bind above.
        _, user_conn = _open_server_and_connection(
            settings, user=user_dn, password=password,
            connect_timeout=timeout_s, receive_timeout=timeout_s,
            trace=trace, bind_label="bind_user",
        )
        user_conn.unbind()

        user_info = {
            "username": str(getattr(user_entry, username_attr, username)),
            "email": str(getattr(user_entry, email_attr, "")),
            "full_name": str(getattr(user_entry, fullname_attr, "")),
        }

        logger.info(f"LDAP authentication successful for: {username}")
        _emit_trace(trace, username, ok=True)
        return user_info

    except Exception as e:
        logger.warning(f"LDAP authentication failed for {username}: {e}")
        _trace_step(trace, "auth_exception", False,
                    f"{e.__class__.__name__}: {e}")
        _emit_trace(trace, username, ok=False)
        return None


def authenticate_ldap_with_trace(
    username: str,
    password: str,
    settings: Dict[str, str],
) -> tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
    """Run a full ``authenticate_ldap`` with tracing forced on and
    return ``(user_info_or_None, trace)`` so the caller can render the
    per-step trace directly (used by the admin "Test Login" endpoint).

    Trace never contains passwords — see ``_trace_step`` callers.
    """
    trace: List[Dict[str, Any]] = []
    user_info: Optional[Dict[str, Any]] = None

    # authenticate_ldap builds its own trace when debug=True and hands
    # it to _emit_trace. We need the raw list, so re-implement the
    # dispatch by temporarily swapping in a collector that captures the
    # trace before logging. Simpler than plumbing an out-param through
    # every callsite.
    global _emit_trace  # noqa: PLW0603
    original_emit = _emit_trace

    def _capture(t, u, *, ok):
        if t:
            trace.extend(t)
        original_emit(t, u, ok=ok)

    _emit_trace = _capture
    try:
        user_info = authenticate_ldap(username, password, settings, debug=True)
    finally:
        _emit_trace = original_emit
    return user_info, trace


def _emit_trace(trace: Optional[List[Dict[str, Any]]], username: str, *,
                ok: bool) -> None:
    """Log a captured trace to the standard logger. Prefixed so operators
    can grep ``[LDAP DEBUG]`` in container logs."""
    if not trace:
        return
    result = "SUCCESS" if ok else "FAILED"
    logger.info("[LDAP DEBUG] %s auth for %r — %d step(s):", result, username, len(trace))
    for step in trace:
        marker = "✓" if step.get("ok") else "✗"
        elapsed = f" ({step['elapsed_ms']}ms)" if "elapsed_ms" in step else ""
        logger.info("[LDAP DEBUG]   %s %s%s: %s",
                    marker, step.get("step"), elapsed, step.get("message"))


def test_ldap_connection(settings: Dict[str, str], *,
                         debug: bool = False) -> Dict[str, Any]:
    """
    Test LDAP connectivity and return status.

    Returns ``{"success": bool, "message": str, "trace": [...]}`` when
    ``debug`` is True; the ``trace`` key is omitted otherwise so we don't
    surface implementation detail unless the admin explicitly asked for it
    via the debug toggle.
    """
    trace: Optional[List[Dict[str, Any]]] = [] if debug else None
    try:
        import ldap3  # noqa: F401
    except ImportError:
        _trace_step(trace, "import_ldap3", False, "ldap3 package missing")
        return _test_response(False, "ldap3 package not installed", trace)

    server_url = settings.get("server_url", "")
    bind_dn = settings.get("bind_dn", "")
    bind_password = settings.get("bind_password", "")

    if not server_url:
        _trace_step(trace, "validate_settings", False, "server_url is empty")
        return _test_response(False, "Server URL is required", trace)
    _trace_step(trace, "validate_settings", True,
                f"server_url={server_url!r}, bind_dn={bind_dn!r}, "
                f"bind_password={'set' if bind_password else 'empty'}")

    try:
        _, conn = _open_server_and_connection(
            settings, user=bind_dn, password=bind_password,
            connect_timeout=10, receive_timeout=10,
            trace=trace, bind_label="bind_service",
        )
        conn.unbind()
        return _test_response(
            True,
            f"Successfully connected to {server_url} (tls_mode={_resolve_tls_mode(settings)})",
            trace,
        )
    except Exception as e:
        return _test_response(False, str(e), trace)


def _test_response(success: bool, message: str,
                   trace: Optional[List[Dict[str, Any]]]) -> Dict[str, Any]:
    out: Dict[str, Any] = {"success": success, "message": message}
    if trace is not None:
        out["trace"] = trace
    return out
