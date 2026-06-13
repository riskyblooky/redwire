"""ActionSchema validator regressions (GHSA-3ccf-qpj4-vpx8 follow-ups).

The recipient list itself is the intended feature surface — rule authors
with AUTOMATION_CREATE / AUTOMATION_EDIT choose recipients. These tests
confirm the *typo* and *malformed-input* guards we wired around it:

  - user_ids / tag_ids must be UUID-shaped at save time
  - role must name a real UserRole value
  - recipients must look like email addresses
  - AUTOMATION_EMAIL_DOMAIN_ALLOWLIST, when set, rejects out-of-list domains
"""

from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError

from routers.automations import ActionSchema


def _u() -> str:
    return str(uuid.uuid4())


# ── user_ids / tag_ids UUID shape ─────────────────────────────────────────


def test_user_ids_accepts_uuid_list():
    a = ActionSchema(type="notify_users", user_ids=[_u(), _u()])
    assert len(a.user_ids) == 2


def test_user_ids_rejects_non_uuid_string():
    with pytest.raises(ValidationError) as exc:
        ActionSchema(type="notify_users", user_ids=["jdoe"])
    assert "not a UUID" in str(exc.value)


def test_user_ids_rejects_partial_uuid():
    with pytest.raises(ValidationError):
        ActionSchema(type="notify_users", user_ids=["abc-def"])


def test_user_ids_allows_none():
    # Pure shape — None means "this action doesn't use user_ids" (e.g. add_tags).
    a = ActionSchema(type="add_tags", user_ids=None, tag_ids=[_u()])
    assert a.user_ids is None


def test_tag_ids_uses_same_validator():
    with pytest.raises(ValidationError):
        ActionSchema(type="add_tags", tag_ids=["my-cool-tag"])


# ── role typo guard ───────────────────────────────────────────────────────


@pytest.mark.parametrize("role", ["admin", "team_lead", "operator", "read_only"])
def test_role_accepts_known_values(role):
    a = ActionSchema(type="notify_role", role=role)
    assert a.role == role


@pytest.mark.parametrize("role", ["Admin", "ADMIN", "team-lead", "lead", "TeamLead", ""])
def test_role_rejects_unknown(role):
    with pytest.raises(ValidationError) as exc:
        ActionSchema(type="notify_role", role=role)
    assert "unknown role" in str(exc.value)


# ── recipients shape ──────────────────────────────────────────────────────


def test_recipients_accepts_real_addresses():
    a = ActionSchema(type="email", recipients=["alice@example.com", "bob@corp.net"])
    assert a.recipients == ["alice@example.com", "bob@corp.net"]


@pytest.mark.parametrize(
    "addr",
    [
        "alice",                  # no @ at all (forgot the domain)
        "alice@",                 # no domain part
        "@example.com",           # no local part
        "alice@example",          # no dot after @
        "alice example.com",      # space
        "alice@example.com,bob",  # comma — they tried to pass two in one string
    ],
)
def test_recipients_rejects_malformed(addr):
    with pytest.raises(ValidationError) as exc:
        ActionSchema(type="email", recipients=[addr])
    assert "not a valid email address" in str(exc.value)


# ── recipient domain allowlist ────────────────────────────────────────────


def test_recipients_allowlist_passes_listed_domain(monkeypatch):
    monkeypatch.setenv("AUTOMATION_EMAIL_DOMAIN_ALLOWLIST", "corp.com,partner.org")
    a = ActionSchema(type="email", recipients=["alice@corp.com", "bob@partner.org"])
    assert len(a.recipients) == 2


def test_recipients_allowlist_rejects_outside_domain(monkeypatch):
    monkeypatch.setenv("AUTOMATION_EMAIL_DOMAIN_ALLOWLIST", "corp.com")
    with pytest.raises(ValidationError) as exc:
        ActionSchema(type="email", recipients=["alice@evil.com"])
    assert "not on AUTOMATION_EMAIL_DOMAIN_ALLOWLIST" in str(exc.value)


def test_recipients_allowlist_unset_preserves_behaviour(monkeypatch):
    monkeypatch.delenv("AUTOMATION_EMAIL_DOMAIN_ALLOWLIST", raising=False)
    # No restriction when the env var is unset — current behaviour.
    a = ActionSchema(type="email", recipients=["alice@anywhere.example"])
    assert a.recipients == ["alice@anywhere.example"]


def test_recipients_allowlist_empty_string_means_unset(monkeypatch):
    monkeypatch.setenv("AUTOMATION_EMAIL_DOMAIN_ALLOWLIST", "   ")
    a = ActionSchema(type="email", recipients=["alice@anywhere.example"])
    assert a.recipients == ["alice@anywhere.example"]


def test_recipients_allowlist_is_case_insensitive(monkeypatch):
    monkeypatch.setenv("AUTOMATION_EMAIL_DOMAIN_ALLOWLIST", "Corp.COM")
    a = ActionSchema(type="email", recipients=["Alice@CORP.com"])
    assert a.recipients == ["Alice@CORP.com"]
