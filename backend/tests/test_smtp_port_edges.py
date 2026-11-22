"""SMTP: a blank / invalid port falls back to 587 instead of raising, and
port 465 always uses implicit TLS (plain SMTP there waited out the timeout)."""

from __future__ import annotations

import smtplib

from utils import email_service


def test_blank_port_defaults():
    assert [email_service.smtp_port(v) for v in ("", None, "abc", "0", "2525")] == [587, 587, 587, 587, 2525]


def test_465_is_implicit_tls_even_unticked(monkeypatch):
    used = []

    class Fake:
        def __init__(self, *a, **kw):
            used.append(type(self).__name__)

        def login(self, *a): pass
        def sendmail(self, *a): pass
        def quit(self): pass
        def starttls(self, **kw): pass

    class SMTP_SSL(Fake): pass
    class SMTP(Fake): pass
    monkeypatch.setattr(smtplib, "SMTP_SSL", SMTP_SSL)
    monkeypatch.setattr(smtplib, "SMTP", SMTP)
    email_service._send_smtp(host="h", port=465, username="", password="", use_tls=False,
                             from_email="a@b.c", from_name="", to_email="x@y.z", subject="s",
                             html_body="<p>x</p>", text_body="x")
    assert used == ["SMTP_SSL"]
