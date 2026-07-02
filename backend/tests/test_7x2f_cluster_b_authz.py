"""GHSA-7x2f-ff7r-h388 cluster B — authorization / scoping gates.

Five sub-issues shipped:

  #1  (CWE-863) `is_creator` short-circuit lets ex-members write.
      Fix: new `is_engagement_member` helper gates the creator bypass
      at three router sites.
  #5  (CWE-602) AI chatbot mode selectable client-side, `chatbot_enabled`
      server flag not enforced. Fix: `/chat` refuses when
      `field_context.resourceType == "chatbot"` and the admin has
      chatbot_enabled=false.
  #6  (CWE-862) Spray-commit auto-creates Assets under VAULT_CREATE
      gate; ASSET_CREATE bypass. Fix: additional ASSET_CREATE check
      when `create_missing_assets=true`.
  #7  (CWE-200) `GET /plugins/` returned admin-configured manifest to
      any authenticated user. Fix: admin-only via
      `require_roles(ADMIN_ROLES)`.
  #11 (CWE-178) Admin-create email path used raw `str`; self-register
      used `EmailStr`. Fix: unify on EmailStr + `.strip().lower()`
      canonicalisation.

Bigger issues (#8 enum bypass on import, #12 version-history race,
#14 runbook-apply commit ordering) are deferred to the follow-up
review — captured in the todo.
"""

from __future__ import annotations

import os

import pytest
from pydantic import ValidationError
from cryptography.fernet import Fernet

os.environ.setdefault("TOTP_ENCRYPTION_KEY", Fernet.generate_key().decode())
os.environ.setdefault("VAULT_ENCRYPTION_KEY", Fernet.generate_key().decode())


# ── Issue 1: is_engagement_member helper ─────────────────────────────


class TestIsEngagementMemberHelperExists:
    """Regression pin: the helper is what all three site-fixes rely on.
    A future maintainer inlining the query or deleting the helper
    should trip this test."""

    def test_helper_importable(self):
        from auth.rbac import is_engagement_member
        assert callable(is_engagement_member)


class TestIsCreatorBypassRefactor:
    """The three vulnerable sites all now follow the pattern:
        if is_creator:
            if not await is_engagement_member(...):
                raise 403
        else:
            check_engagement_permission(...)
    Pin by grep so a future refactor that drops the membership check
    reappears loudly here."""

    def test_discussions_update_thread_uses_membership_gate(self):
        src = open("/app/routers/discussions.py").read()
        assert "is_engagement_member" in src, "helper not used in discussions.py"
        # The two vulnerable sites — update_thread and toggle_resolve —
        # must each contain the membership gate.
        assert src.count("is_engagement_member(") >= 2

    def test_testcases_uses_membership_gate(self):
        src = open("/app/routers/testcases.py").read()
        assert "is_engagement_member" in src


# ── Issue 5: chatbot_enabled server-side enforcement ─────────────────


class TestChatbotEnabledEnforced:
    def test_gate_present_in_chat_handler(self):
        src = open("/app/routers/ai.py").read()
        # Pin the specific 403 message this fix emits — that's the
        # concrete reject shape. Also assert it appears in the
        # ai_chat function's slice (after `async def ai_chat` and
        # before the `mcp_enabled =` MCP-dispatch line).
        marker = '"AI chatbot is disabled on this instance."'
        assert marker in src
        chat_idx = src.find("async def ai_chat")
        loop_idx = src.find("mcp_enabled = ")
        marker_idx = src.find(marker)
        assert chat_idx < marker_idx < loop_idx, (
            "chatbot_enabled 403 must be inside ai_chat and before MCP dispatch"
        )


# ── Issue 6: spray ASSET_CREATE check ────────────────────────────────


class TestSprayAssetCreatePermission:
    def test_asset_create_check_present(self):
        src = open("/app/routers/spray.py").read()
        # The commit endpoint must additionally check ASSET_CREATE when
        # the caller opts into create_missing_assets.
        assert "Permission.ASSET_CREATE" in src
        assert "create_missing_assets" in src


# ── Issue 7: plugins admin-only ──────────────────────────────────────


class TestPluginsListAdminOnly:
    def test_list_endpoint_has_admin_gate(self):
        src = open("/app/routers/plugins.py").read()
        # Both list and detail endpoints require ADMIN_ROLES.
        assert 'require_roles(ADMIN_ROLES)' in src
        # Regression pin: at least 2 endpoints protected (list + detail)
        assert src.count("require_roles(ADMIN_ROLES)") >= 2


# ── Issue 11: email canonicalization symmetry ────────────────────────


class TestEmailNormalizationParity:
    """Both admin-create and self-register must produce the same
    canonical email so uniqueness checks match under case variation."""

    def test_self_register_lowercases_email(self):
        from schemas.user import UserCreate
        u = UserCreate(username="alice", email="Foo@BAR.com", password="passw0rd")
        assert u.email == "foo@bar.com"

    def test_self_register_strips_email(self):
        from schemas.user import UserCreate
        u = UserCreate(username="alice", email="  foo@bar.com  ", password="passw0rd")
        assert u.email == "foo@bar.com"

    def test_admin_create_lowercases_email(self):
        # Test through the same shape the admin endpoint uses.
        from routers.admin import AdminUserCreate
        u = AdminUserCreate(username="alice", email="Foo@BAR.com", password="passw0rd")
        assert u.email == "foo@bar.com"

    def test_admin_create_uses_emailstr_validation(self):
        # Reject shapes that self-register would also reject — this
        # was the specific asymmetry the CVE named.
        from routers.admin import AdminUserCreate
        with pytest.raises(ValidationError):
            AdminUserCreate(username="alice", email="not-an-email", password="passw0rd")
