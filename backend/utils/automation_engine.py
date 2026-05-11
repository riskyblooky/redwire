"""Automation rule evaluation engine.

Called from create_activity_log after every event.  Loads all enabled rules
matching the trigger_type, evaluates conditions against the event context,
and executes matched actions.
"""

import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


# ── condition evaluation ──────────────────────────────────────────────

def _to_float(val: Any) -> Optional[float]:
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _expected_to_list(expected: Any) -> List[str]:
    """Normalize an expected condition value into a list of lowercased strings.

    Accepts an actual list, or a comma-separated string.
    """
    if isinstance(expected, (list, tuple, set)):
        return [str(v).strip().lower() for v in expected if str(v).strip()]
    if expected is None:
        return []
    return [v.strip().lower() for v in str(expected).split(",") if v.strip()]


def _match_condition(condition: dict, context: Dict[str, Any]) -> bool:
    """Evaluate a single condition against the event context.

    Supports scalar operators (equals/not_equals/contains/in) and numeric
    operators (gt/gte/lt/lte) for things like cvss_score. List-typed
    actuals (e.g. tags = ["critical","sqli"]) get the multi-value
    operators has_any/has_all/has_none, plus sensible fallbacks for the
    scalar operators.
    """
    field = condition.get("field", "")
    operator = condition.get("operator", "equals")
    expected = condition.get("value", "")

    actual = context.get(field)

    # Try to also pull from a nested "details" string (which may contain
    # key: value pairs in the change summary)
    if actual is None and "details" in context and isinstance(context["details"], str):
        match = re.search(rf"{field}:\s*\S+\s*→\s*(\S+)", context["details"])
        if match:
            actual = match.group(1)

    if actual is None:
        print(f"  [AUTOMATION] Condition '{field} {operator} {expected}' → field not found in context")
        return False

    # ── numeric operators ──────────────────────────────────────────────
    if operator in ("gt", "gte", "lt", "lte"):
        a_num = _to_float(actual)
        e_num = _to_float(expected)
        if a_num is None or e_num is None:
            result = False
        elif operator == "gt":
            result = a_num > e_num
        elif operator == "gte":
            result = a_num >= e_num
        elif operator == "lt":
            result = a_num < e_num
        else:  # lte
            result = a_num <= e_num
        print(f"  [AUTOMATION] Condition '{field} {operator} {expected}' → actual={actual} → {'MATCH' if result else 'NO MATCH'}")
        return result

    # ── list-typed actual (e.g. tags) ──────────────────────────────────
    if isinstance(actual, (list, tuple, set)):
        actual_list = [str(v).lower() for v in actual]
        expected_list = _expected_to_list(expected)
        if operator == "has_any" or operator == "in":
            result = any(e in actual_list for e in expected_list)
        elif operator == "has_all":
            result = all(e in actual_list for e in expected_list) if expected_list else True
        elif operator == "has_none" or operator == "not_equals":
            result = not any(e in actual_list for e in expected_list)
        elif operator == "equals":
            # equals on a list = the single expected value is present
            single = (expected_list[0] if expected_list else "")
            result = single in actual_list
        elif operator == "contains":
            # contains: substring match against any element
            result = any(str(expected).lower() in v for v in actual_list)
        else:
            result = False
        print(f"  [AUTOMATION] Condition '{field} {operator} {expected}' → actual={actual_list} → {'MATCH' if result else 'NO MATCH'}")
        return result

    # ── scalar string ops ──────────────────────────────────────────────
    actual_str = str(actual).lower()
    expected_str = str(expected).lower()

    if operator == "equals":
        result = actual_str == expected_str
    elif operator == "not_equals":
        result = actual_str != expected_str
    elif operator == "contains":
        result = expected_str in actual_str
    elif operator == "in":
        values = [v.strip().lower() for v in expected_str.split(",")]
        result = actual_str in values
    elif operator == "has_any":
        values = [v.strip().lower() for v in expected_str.split(",")]
        result = actual_str in values
    elif operator == "has_none":
        values = [v.strip().lower() for v in expected_str.split(",")]
        result = actual_str not in values
    else:
        result = False

    print(f"  [AUTOMATION] Condition '{field} {operator} {expected}' → actual='{actual_str}' expected='{expected_str}' → {'MATCH' if result else 'NO MATCH'}")
    return result


def _all_conditions_match(conditions: List[dict], context: Dict[str, Any]) -> bool:
    """All conditions must match (AND logic)."""
    if not conditions:
        return True  # No conditions = always match
    return all(_match_condition(c, context) for c in conditions)


# ── action executors ──────────────────────────────────────────────────

_RESOURCE_LINK_MAP = {
    "finding": "/findings/{resource_id}?engagementId={engagement_id}",
    "testcase": "/testcases/{resource_id}",
    "test_case": "/testcases/{resource_id}",
    "asset": "/assets/{resource_id}",
    "note": "/engagements/{engagement_id}?tab=notes",
    "vault": "/engagements/{engagement_id}?tab=vault",
    "cleanup_artifact": "/engagements/{engagement_id}?tab=cleanup",
}


def _build_resource_link(context: Dict[str, Any]) -> Optional[str]:
    """Build a deep link to the specific resource from automation context."""
    resource_type = context.get("resource_type", "")
    resource_id = context.get("resource_id", "")
    engagement_id = context.get("engagement_id", "")

    template = _RESOURCE_LINK_MAP.get(resource_type)
    if template and resource_id:
        return template.format(resource_id=resource_id, engagement_id=engagement_id)

    # Fallback to engagement
    if engagement_id:
        return f"/engagements/{engagement_id}"

    return None


async def _execute_notify_users(
    db: AsyncSession, action: dict, context: Dict[str, Any], rule_name: str
):
    """Send in-app notification to specific users."""
    from utils.collaboration import create_notification

    user_ids = action.get("user_ids", [])
    message = action.get("message", f"Automation '{rule_name}' triggered")
    link = context.get("link")

    # Build a deep link from context if not provided
    if not link:
        link = _build_resource_link(context)

    for uid in user_ids:
        await create_notification(
            db=db,
            user_id=uid,
            event_type="automation",
            title=f"⚡ {rule_name}",
            message=message,
            link=link,
            actor_id=context.get("user_id"),
            engagement_id=context.get("engagement_id"),
            skip_self_check=True,
        )


async def _execute_notify_role(
    db: AsyncSession, action: dict, context: Dict[str, Any], rule_name: str
):
    """Send notification to all users with a given role."""
    from models.user import User
    from utils.collaboration import create_notification

    role = action.get("role", "admin")
    message = action.get("message", f"Automation '{rule_name}' triggered")
    link = context.get("link")
    if not link:
        link = _build_resource_link(context)

    result = await db.execute(
        select(User.id).where(User.role == role, User.is_active == True)
    )
    user_ids = [r[0] for r in result.all()]

    for uid in user_ids:
        await create_notification(
            db=db,
            user_id=uid,
            event_type="automation",
            title=f"⚡ {rule_name}",
            message=message,
            link=link,
            actor_id=context.get("user_id"),
            engagement_id=context.get("engagement_id"),
        )


async def _execute_webhook(action: dict, context: Dict[str, Any], rule_name: str):
    """Fire an HTTP request to an external URL."""
    url = action.get("url")
    if not url:
        logger.warning("Webhook action missing URL, skipping")
        return

    method = action.get("method", "POST").upper()
    headers = action.get("headers", {})
    body_template = action.get("body_template", "")

    # Simple template variable substitution
    body = body_template
    for key, val in context.items():
        body = body.replace(f"{{{{{key}}}}}", str(val) if val is not None else "")

    # If no template, send context as JSON
    if not body_template:
        import json
        body = json.dumps({
            "rule": rule_name,
            "trigger": context.get("action"),
            "resource_type": context.get("resource_type"),
            "resource_name": context.get("resource_name"),
            "engagement_id": context.get("engagement_id"),
            "details": context.get("details"),
        })
        if "Content-Type" not in headers:
            headers["Content-Type"] = "application/json"

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            if method == "GET":
                await client.get(url, headers=headers)
            else:
                await client.request(method, url, headers=headers, content=body)
        logger.info(f"Webhook fired for rule '{rule_name}' → {url}")
    except Exception as e:
        logger.error(f"Webhook failed for rule '{rule_name}': {e}")


async def _execute_add_tags(
    db: AsyncSession, action: dict, context: Dict[str, Any], rule_name: str
):
    """Apply tags to the resource that triggered the rule.

    Currently supports finding and testcase resource types, since those are
    the only resources with a `tags` relationship today.
    """
    from sqlalchemy import select
    from models.finding import Tag

    resource_type = context.get("resource_type", "")
    resource_id = context.get("resource_id")
    tag_ids = action.get("tag_ids") or []

    if not tag_ids or not resource_id:
        logger.warning(f"add_tags action in '{rule_name}' missing tag_ids or resource_id")
        return

    tag_result = await db.execute(select(Tag).where(Tag.id.in_(tag_ids)))
    tags = tag_result.scalars().all()
    if not tags:
        logger.warning(f"add_tags action in '{rule_name}': none of {tag_ids} resolved to tags")
        return

    if resource_type == "finding":
        from models.finding import Finding
        from sqlalchemy.orm import selectinload
        result = await db.execute(
            select(Finding).where(Finding.id == resource_id).options(selectinload(Finding.tags))
        )
        target = result.scalar_one_or_none()
    elif resource_type == "testcase":
        from models.testcase import TestCase
        from sqlalchemy.orm import selectinload
        result = await db.execute(
            select(TestCase).where(TestCase.id == resource_id).options(selectinload(TestCase.tags))
        )
        target = result.scalar_one_or_none()
    else:
        logger.warning(f"add_tags action in '{rule_name}': unsupported resource_type '{resource_type}'")
        return

    if not target:
        logger.warning(f"add_tags action in '{rule_name}': {resource_type} {resource_id} not found")
        return

    existing_ids = {t.id for t in (target.tags or [])}
    added = 0
    for tag in tags:
        if tag.id not in existing_ids:
            target.tags.append(tag)
            added += 1
    if added:
        logger.info(f"add_tags fired by '{rule_name}': added {added} tag(s) to {resource_type} {resource_id}")


async def _execute_email(
    db: AsyncSession, action: dict, context: Dict[str, Any], rule_name: str
):
    """Fire an email using the SMTP service."""
    from utils.email_service import send_email

    recipients = action.get("recipients", [])
    if isinstance(recipients, str):
        recipients = [r.strip() for r in recipients.split(",") if r.strip()]

    if not recipients:
        logger.warning(f"Email action in rule '{rule_name}' has no recipients. Skipping.")
        return

    subject_template = action.get("subject", f"RedWire Automation: {rule_name}")
    body_template = action.get("body_template", "")

    # Template variable substitution
    subject = subject_template
    body = body_template
    for key, val in context.items():
        placeholder = f"{{{{{key}}}}}"
        str_val = str(val) if val is not None else ""
        subject = subject.replace(placeholder, str_val)
        body = body.replace(placeholder, str_val)

    if not body:
        import json
        body = json.dumps({
            "rule": rule_name,
            "trigger": context.get("action"),
            "resource_type": context.get("resource_type"),
            "resource_name": context.get("resource_name"),
            "engagement_id": context.get("engagement_id"),
            "details": context.get("details"),
        }, indent=2)

    # Wrap basic text in HTML for HTML body
    html_body = f"<pre style='font-family: monospace; padding: 16px; background: #f8f9fa; border-radius: 8px;'>{body}</pre>"

    try:
        for to_email in recipients:
            await send_email(db, to_email, subject, html_body, text_body=body)
        logger.info(f"Email action executed for rule '{rule_name}' → {recipients}")
    except Exception as e:
        logger.error(f"Email action failed for rule '{rule_name}': {e}")


# ── main entry point ──────────────────────────────────────────────────

_ACTION_EXECUTORS = {
    "notify_users": _execute_notify_users,
    "notify_role": _execute_notify_role,
    "webhook": _execute_webhook,
    "email": _execute_email,
    "add_tags": _execute_add_tags,
}


async def execute_rule_actions(
    db: AsyncSession,
    rule: Any,
    context: Dict[str, Any],
) -> None:
    """Execute all actions for a single rule and update its trigger stats.

    Can be called directly (e.g. from a /run endpoint) or from evaluate_rules().
    Does NOT commit — the caller is responsible for committing.
    """
    actions = rule.actions or []
    print(f"[AUTOMATION] Executing {len(actions)} action(s) for rule '{rule.name}'")

    for action_config in actions:
        action_type = action_config.get("type")
        executor = _ACTION_EXECUTORS.get(action_type)
        if not executor:
            print(f"[AUTOMATION] Unknown action type '{action_type}' in rule '{rule.name}'")
            continue

        try:
            if action_type in ("notify_users", "notify_role", "email", "add_tags"):
                await executor(db, action_config, context, rule.name)
            else:
                await executor(action_config, context, rule.name)
            print(f"[AUTOMATION] Action '{action_type}' executed successfully")
        except Exception as e:
            print(f"[AUTOMATION] Action '{action_type}' FAILED: {e}")
            logger.error(f"Action '{action_type}' failed in rule '{rule.name}': {e}")

    # Update trigger stats
    rule.last_triggered_at = datetime.utcnow()
    rule.trigger_count = (rule.trigger_count or 0) + 1


async def evaluate_rules(
    db: AsyncSession,
    trigger_type: str,
    context: Dict[str, Any],
):
    """Evaluate all enabled automation rules matching the trigger_type.

    Called from create_activity_log after every event.
    """
    from models.automation import AutomationRule

    # Manual-only rules are never triggered automatically
    if trigger_type == "manual":
        return

    try:
        result = await db.execute(
            select(AutomationRule).where(
                AutomationRule.trigger_type == trigger_type,
                AutomationRule.is_enabled == True,
            )
        )
        rules = result.scalars().all()

        print(f"[AUTOMATION] evaluate_rules: trigger='{trigger_type}', found {len(rules)} rule(s), context keys={list(context.keys())}")
        if context.get('status'):
            print(f"[AUTOMATION]   context status='{context.get('status')}', severity='{context.get('severity')}'")

        for rule in rules:
            conditions = rule.conditions or []

            print(f"[AUTOMATION] Evaluating rule '{rule.name}' with {len(conditions)} condition(s)")

            if not _all_conditions_match(conditions, context):
                print(f"[AUTOMATION] Rule '{rule.name}' → conditions did NOT match, skipping")
                continue

            print(f"[AUTOMATION] Rule '{rule.name}' → MATCHED! Executing actions")
            await execute_rule_actions(db, rule, context)

        # Note: do NOT commit here — caller (create_activity_log) commits
        # after all rule evaluations complete

    except Exception as e:
        print(f"[AUTOMATION] ENGINE ERROR: {e}")
        import traceback
        traceback.print_exc()
        logger.error(f"Automation engine error: {e}")

