"""Fire-time email domain allowlist tests (GHSA-3ccf-qpj4-vpx8 follow-up).

The save-time check in `ActionSchema._validate_recipients` is already
covered in `test_action_schema_validators.py`. The save-time check is
not enough on its own — a rule that was saved before the allowlist
tightened still gets a runtime check. These tests cover that second
gate inside `_execute_email`.

`send_email` is monkey-patched so we never touch SMTP; we just record
which addresses the engine *would* have delivered to.
"""

from __future__ import annotations

import asyncio
from typing import List

import pytest

import utils.automation_engine as engine


class _RecordingSink:
    """Replacement for utils.email_service.send_email — records calls."""

    def __init__(self):
        self.calls: List[str] = []

    async def __call__(self, db, to_email, subject, html_body, text_body=None):
        self.calls.append(to_email)


@pytest.fixture
def sink(monkeypatch):
    s = _RecordingSink()
    # send_email is imported inside _execute_email, so we patch the source
    # module — the local import resolves to the patched object.
    import utils.email_service
    monkeypatch.setattr(utils.email_service, "send_email", s)
    return s


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_no_env_var_delivers_to_all_recipients(sink, monkeypatch):
    monkeypatch.delenv("AUTOMATION_EMAIL_DOMAIN_ALLOWLIST", raising=False)
    action = {
        "recipients": ["a@corp.com", "b@evil.com"],
        "subject": "hi",
        "body_template": "body",
    }
    _run(engine._execute_email(db=None, action=action, context={}, rule_name="r"))
    assert sink.calls == ["a@corp.com", "b@evil.com"]


def test_allowlist_filters_outside_domain(sink, monkeypatch):
    monkeypatch.setenv("AUTOMATION_EMAIL_DOMAIN_ALLOWLIST", "corp.com")
    action = {
        "recipients": ["a@corp.com", "b@evil.com"],
        "subject": "hi",
        "body_template": "body",
    }
    _run(engine._execute_email(db=None, action=action, context={}, rule_name="r"))
    assert sink.calls == ["a@corp.com"]


def test_allowlist_skips_send_when_all_filtered(sink, monkeypatch):
    monkeypatch.setenv("AUTOMATION_EMAIL_DOMAIN_ALLOWLIST", "corp.com")
    action = {
        "recipients": ["a@evil.com", "b@evil.com"],
        "subject": "hi",
        "body_template": "body",
    }
    _run(engine._execute_email(db=None, action=action, context={}, rule_name="r"))
    assert sink.calls == []


def test_allowlist_is_case_insensitive(sink, monkeypatch):
    monkeypatch.setenv("AUTOMATION_EMAIL_DOMAIN_ALLOWLIST", "Corp.COM")
    action = {
        "recipients": ["a@CORP.com"],
        "subject": "hi",
        "body_template": "body",
    }
    _run(engine._execute_email(db=None, action=action, context={}, rule_name="r"))
    assert sink.calls == ["a@CORP.com"]


def test_malformed_address_dropped_and_logged(sink, monkeypatch):
    # Save-time validator normally catches this, but a hand-edited DB row
    # could still surface it at fire time. Confirm we drop instead of crash.
    monkeypatch.setenv("AUTOMATION_EMAIL_DOMAIN_ALLOWLIST", "corp.com")
    action = {
        "recipients": ["not-an-address", "a@corp.com"],
        "subject": "hi",
        "body_template": "body",
    }
    _run(engine._execute_email(db=None, action=action, context={}, rule_name="r"))
    assert sink.calls == ["a@corp.com"]
