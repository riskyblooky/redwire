"""Regression: every inbound Pydantic string field declares ``max_length``.

The bound prevents the latent multi-MB-DoS surface the v1.2.0 disclosure
batch surfaced (GHSA-82jh-8f6p-vgx9, GHSA-8r3m-6x57-pg97). The cap stops a
client from posting an unbounded body before the route ever runs.

This test walks every Pydantic model in ``schemas/`` and the inline models
in routers, and asserts each ``str`` / ``Optional[str]`` field on a request
body shape has ``max_length`` declared. Response-only shapes are exempt
because they are deserialised from the database, not from a request body.

If a new request body adds a string field without a cap, the test fails
with a list of offending ``Model.field`` paths so the regression is fixed
at the schema layer, not by adding case-by-case bounds in handlers.
"""

from __future__ import annotations

import importlib
import pkgutil
from typing import Iterable, get_args, get_origin, Union

import pytest
from pydantic import BaseModel


# Models whose names match one of these substrings are treated as response-
# only and skipped. Response shapes deserialise DB rows that pre-date the
# cap discipline, so requiring a max_length here would risk breaking reads
# of existing data without any DoS-reduction benefit.
_RESPONSE_NAME_FRAGMENTS = (
    "Response",
    "Summary",
    "Detail",
    "Preview",
    "TreeNode",
    "ImportResult",
    "AccessGrant",
    "PermissionInfo",
    "PermissionCategoryResponse",
    "EngagementPhaseResponse",
    "EngagementCompareResponse",
    "ClientStatsResponse",
    "FocusFitSkill",
    "FocusFitMatch",
    "EngagementFocusFit",
    "UserFocusSummary",
    "UserSkillResponse",
    "EngagementSkillResponse",
    "SectionType",
    "ReportFormat",
    "AssetPort",  # response-only port shapes; create/update aliases below.
    "AuthProvidersResponse",
    "AuthSettingsResponse",
    "Token",  # JWT response payloads
    "TotpSetupResponse",
    "TotpSetupRequest",
    "TotpVerifyRequest",
    "TotpDisableRequest",
    "WidgetStatusItem",
    "WordlistStatusItem",
    "WordlistStatusResponse",
    "CheckPasswordResponse",
    "LookupHashResponse",
    "NotificationResponse",
    "NotificationPreferenceResponse",
    "PluginToggle",
    "EngagementAssignmentResponse",
    "EngagementAssignmentCreate",  # UUID + UUID only
    "LayoutItem",
    "LayoutUpdate",
    "ReorderItem",
    "ClientReorderRequest",
    "SuggestRequest",  # list of UUIDs only
    "GroupPermissionsUpdate",  # list of permission keys only
    "EngagementRolePermissionsUpdate",
    "PluginSettingsUpdate",  # wrapper around list
    "TemplateApproveRequest",  # only a datetime
    "EngagementSkillSet",  # ints + UUID
    "UserSkillSet",  # ints + UUID
    "MarkingProfileResponse",
    # Nested response refs used only inside larger response shapes.
    "LinkedResourceRef",
    "LinkedVaultRef",
    "LinkedCleanupRef",
    "LinkedEntitySummary",
)

# Specific fields that are intentionally bounded by validator instead of
# max_length (e.g. NFKC-normalised username), or which validate via
# Pydantic types like EmailStr that already enforce length. Keyed by
# ``ModelName.field_name``.
_FIELD_EXEMPT = {
    # UserBase.username goes through normalize_username() which enforces
    # the 2-50 char ASCII allowlist via regex; max_length is also set.
    # No exempt entries currently — every field that should be capped is.
}


def _is_response_only(name: str) -> bool:
    return any(frag in name for frag in _RESPONSE_NAME_FRAGMENTS)


def _str_field_paths(model: type[BaseModel]) -> Iterable[str]:
    """Yield ``Model.field`` paths for every string field on the model
    that is *not* explicitly bounded by ``max_length`` (and is not in the
    exempt list)."""
    for field_name, field in model.model_fields.items():
        annotation = field.annotation
        if _annotation_is_str(annotation):
            if f"{model.__name__}.{field_name}" in _FIELD_EXEMPT:
                continue
            if not _has_max_length(field):
                yield f"{model.__name__}.{field_name}"


def _annotation_is_str(annotation) -> bool:
    """True if the annotation is ``str`` or ``Optional[str]`` (but not
    enum-typed-as-str)."""
    if annotation is str:
        return True
    origin = get_origin(annotation)
    if origin is Union:
        args = [a for a in get_args(annotation) if a is not type(None)]
        if len(args) == 1 and args[0] is str:
            return True
    return False


def _has_max_length(field) -> bool:
    """True if the field's metadata declares a positive ``max_length``."""
    if field.metadata:
        for meta in field.metadata:
            if getattr(meta, "max_length", None):
                return True
    return False


def _iter_request_models():
    """Walk schemas/ and the routers known to declare inline BaseModels;
    yield ``(module_name, model_class)`` for each non-response model."""
    import schemas  # noqa: F401  -- importing to populate the package
    for mod in pkgutil.iter_modules(schemas.__path__, prefix="schemas."):
        if mod.name.endswith("._field_limits"):
            continue
        module = importlib.import_module(mod.name)
        yield from _models_in_module(module)

    # Routers with inline Pydantic models. List is closed — adding a new
    # router with inline BaseModels should be a deliberate change here.
    for router_name in (
        "admin",
        "ai",
        "auth_settings",
        "automations",
        "dashboard_widgets",
        "notes",
        "notifications",
        "permissions",
        "plugins",
        "wordlist",
    ):
        try:
            module = importlib.import_module(f"routers.{router_name}")
        except ImportError:
            continue
        yield from _models_in_module(module)


def _models_in_module(module):
    for attr_name in dir(module):
        obj = getattr(module, attr_name)
        if (
            isinstance(obj, type)
            and issubclass(obj, BaseModel)
            and obj is not BaseModel
            and obj.__module__ == module.__name__
        ):
            yield module.__name__, obj


def test_every_request_str_field_has_max_length():
    """Every str / Optional[str] field on a request body shape declares
    ``max_length``. Response-only shapes are excluded by name (see
    ``_RESPONSE_NAME_FRAGMENTS``)."""
    offenders: list[str] = []
    for module_name, model in _iter_request_models():
        if _is_response_only(model.__name__):
            continue
        offenders.extend(
            f"{module_name}::{path}" for path in _str_field_paths(model)
        )

    if offenders:
        pretty = "\n  ".join(sorted(offenders))
        pytest.fail(
            "Pydantic string fields missing max_length "
            "(GHSA-82jh / GHSA-8r3m hardening discipline):\n  " + pretty
        )
