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


def _build_tls_config(settings: Dict[str, str]):
    """Build an ldap3 Tls object from settings.

    Uses CERT_REQUIRED when a CA cert is provided or by default.
    Falls back to CERT_NONE only when tls_verify is explicitly 'false'.
    """
    try:
        from ldap3 import Tls
        import ssl
    except ImportError:
        return None

    ca_cert_pem = settings.get("tls_ca_cert", "").strip()
    tls_verify = settings.get("tls_verify", "true").lower() != "false"

    if ca_cert_pem:
        # Write CA cert to temp file for ssl context
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pem", mode="w")
        tmp.write(ca_cert_pem)
        tmp.close()
        tls_config = Tls(
            validate=ssl.CERT_REQUIRED,
            ca_certs_file=tmp.name,
        )
        return tls_config
    elif tls_verify:
        return Tls(validate=ssl.CERT_REQUIRED)
    else:
        logger.warning("LDAP TLS certificate validation is DISABLED")
        return Tls(validate=ssl.CERT_NONE)


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
        from ldap3 import Server, Connection, ALL, SUBTREE
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
    use_tls = settings.get("tls_enabled", "true").lower() == "true"

    if not server_url or not search_base:
        logger.error("LDAP server_url or search_base not configured")
        return None

    try:
        # Build server with optional TLS
        tls_config = _build_tls_config(settings) if use_tls else None

        server = Server(server_url, get_info=ALL, tls=tls_config)

        # Step 1: Bind with service account to search for user DN
        search_conn = Connection(server, user=bind_dn, password=bind_password, auto_bind=True)

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

        # Step 2: Bind as the user to verify password
        user_conn = Connection(server, user=user_dn, password=password, auto_bind=True)
        user_conn.unbind()

        # Extract attributes
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
        from ldap3 import Server, Connection, ALL
    except ImportError:
        return {"success": False, "message": "ldap3 package not installed"}

    server_url = settings.get("server_url", "")
    bind_dn = settings.get("bind_dn", "")
    bind_password = settings.get("bind_password", "")
    use_tls = settings.get("tls_enabled", "true").lower() == "true"

    if not server_url:
        return {"success": False, "message": "Server URL is required"}

    try:
        tls_config = _build_tls_config(settings) if use_tls else None

        server = Server(server_url, get_info=ALL, tls=tls_config, connect_timeout=10)
        conn = Connection(server, user=bind_dn, password=bind_password, auto_bind=True)

        server_info = str(server.info) if server.info else "Connected"
        conn.unbind()

        return {
            "success": True,
            "message": f"Successfully connected to {server_url}",
        }
    except Exception as e:
        return {"success": False, "message": str(e)}
