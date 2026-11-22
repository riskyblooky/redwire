"""SAML setup edge cases: an unset SP entity id falls back to the metadata
URL instead of an empty entityId, and a missing python3-saml gives
(None, None) — not a bare None the login route fails to unpack."""

from __future__ import annotations

from auth import saml_auth


def test_blank_sp_entity_id_falls_back():
    s = saml_auth.get_saml_settings({"sp_entity_id": ""})
    assert s["sp"]["entityId"].endswith("/auth/saml/metadata")


def test_missing_library_returns_a_pair(monkeypatch):
    import sys
    monkeypatch.setitem(sys.modules, "onelogin.saml2.auth", None)   # import -> ImportError
    assert saml_auth.build_saml_request_url({}) == (None, None)
