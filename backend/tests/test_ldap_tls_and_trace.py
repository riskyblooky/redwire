"""LDAP: a configured CA cert is handed to ldap3 in memory (no temp file
left behind per login), and the admin "Test Login" trace is collected
without swapping the module-level emitter other logins use."""

from __future__ import annotations

import tempfile

from auth import ldap_auth

PEM = "-----BEGIN CERTIFICATE-----\nMIIB\n-----END CERTIFICATE-----"


def test_ca_cert_is_not_written_to_disk(monkeypatch):
    def no_files(*a, **kw):
        raise AssertionError("CA cert written to a temp file")
    monkeypatch.setattr(tempfile, "NamedTemporaryFile", no_files)
    tls = ldap_auth._build_tls_config({"tls_ca_cert": PEM})
    assert tls.ca_certs_data == PEM


def test_trace_does_not_swap_the_module_emitter(monkeypatch):
    seen = []

    def recorder(trace, username, *, ok):
        seen.append(ldap_auth._emit_trace is recorder)   # still the real emitter during the call?
    monkeypatch.setattr(ldap_auth, "_emit_trace", recorder)
    info, trace = ldap_auth.authenticate_ldap_with_trace(
        "u", "p", {"server_url": "ldap://127.0.0.1:1", "tls_mode": "none", "search_base": "dc=x"})
    assert info is None and trace and seen == [True]
