"""Every path that sets a login password refuses one over bcrypt's 72-byte
limit (bcrypt ignores the rest, so such a password was only as strong as
its first 72 bytes): reset, admin create, forced change."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

LONG = "Aa1!" * 19          # 76 bytes


@pytest.mark.parametrize("factory", [
    lambda pw: __import__("schemas.auth_settings", fromlist=["x"]).ResetPasswordRequest(token="t", new_password=pw),
    lambda pw: __import__("routers.admin", fromlist=["x"]).AdminUserCreate(
        username="newuser", email="n@example.com", password=pw),
    lambda pw: __import__("routers.auth", fromlist=["x"]).ForceChangePasswordRequest(current_password="x", new_password=pw),
])
def test_long_password_rejected(factory):
    with pytest.raises(ValidationError, match="72-byte"):
        factory(LONG)
    factory("Aa1!" * 4)     # a normal one still passes
