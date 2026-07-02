"""
LDAP authentication module.
Uses ldap3 to bind and search against an LDAP/Active Directory server.
"""
from typing import Optional, Dict, Any
import logging
import tempfile
import os

logger = logging.getLogger(__name__)


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

    server_kwargs: Dict[str, Any] = {"get_info": ALL}
    if connect_timeout is not None:
        server_kwargs["connect_timeout"] = connect_timeout

    if mode in ("ldaps", "starttls"):
        server_kwargs["tls"] = _build_tls_config(settings)

    server = Server(server_url, **server_kwargs)

    # For starttls: connect + upgrade BEFORE binding, so the bind
    # password isn't leaked over plaintext.
    if mode == "starttls":
        conn = Connection(server, user=user, password=password, auto_bind=False)
        if not conn.open():
            raise RuntimeError(f"LDAP connect failed: {conn.result}")
        if not conn.start_tls():
            raise RuntimeError(f"LDAP StartTLS failed: {conn.result}")
        if not conn.bind():
            raise RuntimeError(f"LDAP bind failed: {conn.result}")
        return server, conn

    # ldaps or plain: single-step auto_bind is fine.
    conn = Connection(server, user=user, password=password, auto_bind=True)
    return server, conn


def authenticate_ldap(
    username: str,
    password: str,
    settings: Dict[str, str],
) -> Optional[Dict[str, Any]]:
    """
    Authenticate a user against LDAP.

    Returns a dict with user info (username, email, full_name) on success,
    or None on failure.
    """
    try:
        from ldap3 import SUBTREE
    except ImportError:
        logger.error("ldap3 package not installed")
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
        return None

    try:
        # Step 1: Bind with service account to search for user DN
        server, search_conn = _open_server_and_connection(
            settings, user=bind_dn, password=bind_password,
        )

        # Escape username to prevent LDAP filter injection, then substitute
        safe_username = _escape_ldap_filter(username)
        actual_filter = search_filter.replace("{username}", safe_username)
        search_conn.search(
            search_base=search_base,
            search_filter=actual_filter,
            search_scope=SUBTREE,
            attributes=[username_attr, email_attr, fullname_attr],
        )

        if not search_conn.entries:
            logger.info(f"LDAP user not found: {username}")
            search_conn.unbind()
            return None

        user_entry = search_conn.entries[0]
        user_dn = str(user_entry.entry_dn)
        search_conn.unbind()

        # Step 2: Bind as the user to verify password. Reopen with the
        # same TLS mode so the user bind is protected the same way as
        # the service bind above.
        _, user_conn = _open_server_and_connection(
            settings, user=user_dn, password=password,
        )
        user_conn.unbind()

        user_info = {
            "username": str(getattr(user_entry, username_attr, username)),
            "email": str(getattr(user_entry, email_attr, "")),
            "full_name": str(getattr(user_entry, fullname_attr, "")),
        }

        logger.info(f"LDAP authentication successful for: {username}")
        return user_info

    except Exception as e:
        logger.warning(f"LDAP authentication failed for {username}: {e}")
        return None


def test_ldap_connection(settings: Dict[str, str]) -> Dict[str, Any]:
    """
    Test LDAP connectivity and return status.
    Returns {"success": bool, "message": str}
    """
    try:
        import ldap3  # noqa: F401
    except ImportError:
        return {"success": False, "message": "ldap3 package not installed"}

    server_url = settings.get("server_url", "")
    bind_dn = settings.get("bind_dn", "")
    bind_password = settings.get("bind_password", "")

    if not server_url:
        return {"success": False, "message": "Server URL is required"}

    try:
        _, conn = _open_server_and_connection(
            settings, user=bind_dn, password=bind_password, connect_timeout=10,
        )
        conn.unbind()
        return {
            "success": True,
            "message": f"Successfully connected to {server_url} (tls_mode={_resolve_tls_mode(settings)})",
        }
    except Exception as e:
        return {"success": False, "message": str(e)}
