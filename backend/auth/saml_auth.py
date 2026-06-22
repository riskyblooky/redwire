"""
SAML 2.0 SSO authentication module.
Uses python3-saml (OneLogin) to generate AuthnRequests, validate responses,
and extract user attributes from SAML assertions.
"""
from typing import Dict, Any, Optional
import logging
import os

logger = logging.getLogger(__name__)

# Base URL for the application — used to construct SP URLs
BASE_URL = os.getenv("BACKEND_URL", "http://localhost:8000")


def get_saml_settings(db_settings: Dict[str, str]) -> Dict[str, Any]:
    """
    Build a python3-saml settings dict from database configuration.
    """
    sp_entity_id = db_settings.get("sp_entity_id", f"{BASE_URL}/auth/saml/metadata")
    acs_url = f"{BASE_URL}/auth/saml/acs"
    sls_url = f"{BASE_URL}/auth/saml/sls"

    return {
        "strict": True,
        "debug": False,
        "sp": {
            "entityId": sp_entity_id,
            "assertionConsumerService": {
                "url": acs_url,
                "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST",
            },
            "singleLogoutService": {
                "url": sls_url,
                "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect",
            },
            "NameIDFormat": "urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress",
        },
        "idp": {
            "entityId": db_settings.get("idp_entity_id", ""),
            "singleSignOnService": {
                "url": db_settings.get("idp_sso_url", ""),
                "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect",
            },
            "singleLogoutService": {
                "url": db_settings.get("idp_slo_url", ""),
                "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect",
            },
            "x509cert": db_settings.get("idp_x509_cert", ""),
        },
        "security": {
            "nameIdEncrypted": False,
            "authnRequestsSigned": False,
            "logoutRequestSigned": False,
            "logoutResponseSigned": False,
            "signMetadata": False,
            "wantMessagesSigned": False,
            "wantAssertionsSigned": True,
            "wantNameIdEncrypted": False,
            "requestedAuthnContext": False,
        },
    }


def build_saml_request_url(db_settings: Dict[str, str], return_to: str = "/") -> Optional[str]:
    """
    Generate a SAML AuthnRequest URL to redirect the user to the IdP.
    Returns the redirect URL or None on error.
    """
    try:
        from onelogin.saml2.auth import OneLogin_Saml2_Auth
    except ImportError:
        logger.error("python3-saml not installed")
        return None

    saml_settings = get_saml_settings(db_settings)

    # Create a minimal request dict for python3-saml
    request_data = _build_request_dict("GET", BASE_URL + "/auth/saml/login", {})

    try:
        auth = OneLogin_Saml2_Auth(request_data, saml_settings)
        redirect_url = auth.login(return_to=return_to)
        # Caller stores this and passes it back to process_saml_response so
        # python3-saml can validate InResponseTo. Without it the ACS accepts
        # unsolicited / replayed Responses.
        return redirect_url, auth.get_last_request_id()
    except Exception as e:
        logger.error(f"Failed to build SAML request: {e}")
        return None, None


def process_saml_response(
    post_data: Dict[str, str],
    db_settings: Dict[str, str],
    request_url: str,
    request_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Validate SAML response and extract user attributes.
    
    Returns dict with keys: email, username, full_name, name_id
    or None on validation failure.
    """
    try:
        from onelogin.saml2.auth import OneLogin_Saml2_Auth
    except ImportError:
        logger.error("python3-saml not installed")
        return None

    saml_settings = get_saml_settings(db_settings)
    request_data = _build_request_dict("POST", request_url, post_data)

    try:
        auth = OneLogin_Saml2_Auth(request_data, saml_settings)
        # Bind the Response to the AuthnRequest we issued. python3-saml
        # validates InResponseTo against this and rejects a mismatch.
        auth.process_response(request_id=request_id)

        errors = auth.get_errors()
        if errors:
            logger.error(f"SAML response errors: {errors}")
            logger.error(f"SAML last error reason: {auth.get_last_error_reason()}")
            return None

        if not auth.is_authenticated():
            logger.warning("SAML response: user not authenticated")
            return None

        # Single-use assertion ID enforcement (GHSA-68hx-hggg-vrr2 follow-up).
        # Atomic SET NX against Redis with TTL = NotOnOrAfter window. A
        # capture-and-replay of the same <Response> within the SAML
        # validity window now lands on the existing key and is refused.
        # Without this, the saml_request_id cookie binding catches IdP-
        # initiated and cross-session replays but not same-flow replays.
        from auth.saml_replay import claim_saml_assertion
        if not claim_saml_assertion(
            auth.get_last_assertion_id(),
            auth.get_last_assertion_not_on_or_after(),
        ):
            # claim_saml_assertion already logs the specific reason
            # (replay / Redis-down / missing-id / expired-window).
            return None

        attributes = auth.get_attributes()
        name_id = auth.get_nameid()

        # Try to extract common attributes
        email = (
            _first(attributes.get("email"))
            or _first(attributes.get("http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress"))
            or name_id
        )
        username = (
            _first(attributes.get("username"))
            or _first(attributes.get("http://schemas.xmlsoap.org/ws/2005/05/identity/claims/name"))
            or email.split("@")[0] if email else ""
        )
        full_name = (
            _first(attributes.get("displayName"))
            or _first(attributes.get("http://schemas.xmlsoap.org/ws/2005/05/identity/claims/displayname"))
            or _first(attributes.get("cn"))
            or ""
        )

        return {
            "email": email,
            "username": username,
            "full_name": full_name,
            "name_id": name_id,
        }

    except Exception as e:
        logger.error(f"SAML response processing failed: {e}")
        return None


def generate_sp_metadata(db_settings: Dict[str, str]) -> Optional[str]:
    """Generate SP metadata XML for IdP configuration."""
    try:
        from onelogin.saml2.auth import OneLogin_Saml2_Auth
    except ImportError:
        return None

    saml_settings = get_saml_settings(db_settings)
    request_data = _build_request_dict("GET", BASE_URL + "/auth/saml/metadata", {})

    try:
        auth = OneLogin_Saml2_Auth(request_data, saml_settings)
        metadata = auth.get_settings().get_sp_metadata()

        from onelogin.saml2.utils import OneLogin_Saml2_Utils
        errors = OneLogin_Saml2_Utils.validate_metadata(metadata)
        if errors:
            logger.error(f"SP metadata validation errors: {errors}")
            return None

        return metadata.decode("utf-8") if isinstance(metadata, bytes) else metadata
    except Exception as e:
        logger.error(f"Failed to generate SP metadata: {e}")
        return None


def _build_request_dict(method: str, url: str, data: Dict) -> Dict:
    """Build the request dict expected by python3-saml."""
    from urllib.parse import urlparse
    parsed = urlparse(url)
    return {
        "https": "on" if parsed.scheme == "https" else "off",
        "http_host": parsed.hostname or "localhost",
        "server_port": str(parsed.port or (443 if parsed.scheme == "https" else 80)),
        "script_name": parsed.path,
        "get_data": {},
        "post_data": data,
    }


def _first(lst):
    """Return first element of a list or None."""
    if lst and isinstance(lst, list) and len(lst) > 0:
        return lst[0]
    return None
