"""Automation rule evaluation engine.

Called from create_activity_log after every event.  Loads all enabled rules
matching the trigger_type, evaluates conditions against the event context,
and executes matched actions.
"""

import json
import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import quote as _url_quote
from xml.sax.saxutils import escape as _xml_escape

import httpx
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from utils.ssrf import validate_outbound_url, OutboundURLError

logger = logging.getLogger(__name__)

# Headers stripped from caller-supplied webhook actions so the request can't
# carry attacker-chosen credentials or spoof its origin (GHSA-7f74-569m-w73h).
_BLOCKED_WEBHOOK_HEADERS = {
    "authorization", "proxy-authorization", "cookie", "host",
    "x-forwarded-for", "x-forwarded-host", "x-forwarded-proto", "x-real-ip",
}


# Receiver-rendered chat-platform tokens — neutralised inside JSON-body
# webhook substitutions. GHSA-rvcc follow-up: the original fix closed the
# *structural* breakout primitive (escape `"` so a substituted value can't
# inject sibling JSON keys), but tokens like Slack `<!channel>` and
# `<https://x|click>` are valid JSON string content and survive any JSON
# escape — once delivered, the receiver renders the broadcast / phishing
# hyperlink under the platform integration's identity. Defang is
# conservative: replace the rendering token with a readable literal so
# the textual signal is preserved, only the side effect is removed.
_SLACK_BROADCAST_RE = re.compile(r"<!(channel|here|everyone)>", re.IGNORECASE)
_SLACK_USER_RE = re.compile(r"<@[UW][A-Z0-9]+(?:\|[^>]*)?>")
_SLACK_GROUP_RE = re.compile(r"<!subteam\^[A-Z0-9]+(?:\|([^>]*))?>", re.IGNORECASE)
_SLACK_CHANNEL_RE = re.compile(r"<#[CG][A-Z0-9]+(?:\|([^>]*))?>")
_MRKDWN_LINK_RE = re.compile(r"<(https?://[^|>\s]+)\|([^>]*)>")
_TEAMS_AT_RE = re.compile(r"<at(?:\s+id=\"[^\"]*\")?\s*>([^<]*)</at>", re.IGNORECASE)


def _defang_chat_tokens(val: str) -> str:
    """Neutralise receiver-rendered chat-platform tokens in ``val``.

    Applied before JSON-escaping in :func:`_escape_template_value` so a
    low-privileged user-authored string (finding title, asset name, etc.)
    can't smuggle Slack broadcasts (`<!channel>`), `@user` pings,
    Teams `<at>` mentions, or `<url|text>` hyperlinks past the webhook
    boundary. Defangs in place rather than rejecting so legitimate
    content reads naturally to the recipient.
    """
    if not val or "<" not in val:
        return val
    val = _SLACK_BROADCAST_RE.sub(lambda m: f"[@{m.group(1).lower()}]", val)
    val = _SLACK_USER_RE.sub("[user mention]", val)
    val = _SLACK_GROUP_RE.sub(
        lambda m: f"[group mention: {m.group(1)}]" if m.group(1) else "[group mention]", val
    )
    val = _SLACK_CHANNEL_RE.sub(
        lambda m: f"[channel mention: {m.group(1)}]" if m.group(1) else "[channel mention]", val
    )
    val = _MRKDWN_LINK_RE.sub(lambda m: f"{m.group(2)} ({m.group(1)})", val)
    val = _TEAMS_AT_RE.sub(
        lambda m: f"[mention: {m.group(1).strip()}]" if m.group(1).strip() else "[mention]", val
    )
    return val


def _escape_template_value(val: str, content_type: Optional[str]) -> str:
    """Escape ``val`` for substitution into a webhook body of the given content type.

    Used by :func:`_execute_webhook` to keep low-privileged user input
    (finding/asset/discussion titles, etc.) from breaking out of the
    string position the admin's template placed it in
    (GHSA-rvcc-9pr2-v23q). JSON-body callsites additionally run the value
    through :func:`_defang_chat_tokens` so receiver-rendered Slack/Teams
    tokens can't ride a substituted string into a chat-platform broadcast.
    """
    ct = (content_type or "").lower().split(";", 1)[0].strip()
    if ct == "application/json" or ct.endswith("+json"):
        # json.dumps wraps in quotes; strip them so the admin's surrounding
        # "…" in the template is preserved.
        return json.dumps(_defang_chat_tokens(val))[1:-1]
    if ct in ("application/xml", "text/xml") or ct.endswith("+xml"):
        return _xml_escape(val, {'"': "&quot;", "'": "&apos;"})
    if ct == "application/x-www-form-urlencoded":
        return _url_quote(val, safe="")
    return val


def _looks_like_json_template(template: str, placeholders: List[str]) -> bool:
    """True if the template parses as JSON when each ``{{key}}`` is replaced
    by a JSON-value sentinel — i.e., the admin authored a JSON body.

    Uses ``0`` as the sentinel so it's valid both as a bare value
    (``{"count":0}``) and inside a quoted string (``{"text":"0"}``).
    Requires the template to begin with ``{`` or ``[`` so a bare
    ``{{name}}`` template isn't mis-classified as JSON.
    """
    probe = template
    for key in placeholders:
        probe = probe.replace(f"{{{{{key}}}}}", "0")
    stripped = probe.lstrip()
    if not stripped or stripped[0] not in "{[":
        return False
    try:
        json.loads(probe)
        return True
    except ValueError:
        return False


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

    if actual is None:
        # GHSA-88hm-p8rq-cfw2 follow-up: structured fallback when the
        # post-update value isn't a top-level context key. ``compute_changes_dict``
        # puts {field: {"old": …, "new": …}} under ``context["changes"]``;
        # consult it before giving up. Restores the update-event matching
        # capability that the deleted prose-regex fallback was trying to
        # provide, without ever parsing an attacker-influenced string.
        changes = context.get("changes") or {}
        if field in changes and isinstance(changes[field], dict):
            actual = changes[field].get("new")

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
    db: AsyncSession, action: dict, context: Dict[str, Any], rule_name: str,
    *,
    rule_is_personal: bool = False,
):
    """Send in-app notification to specific users.

    GHSA-jvcx-44v2-gc9m: intersect recipients with users who can see the
    event's engagement. Applies to both scoped and global rules so a global
    rule (admin-curated) can't notify users about engagements they wouldn't
    otherwise see. Fail closed on the check.
    """
    from utils.collaboration import create_notification
    from auth.rbac import check_engagement_permission
    from auth.permissions import has_global_permission
    from models.permission import Permission
    from models.user import User, UserRole
    from sqlalchemy import select

    user_ids = action.get("user_ids", [])
    message = action.get("message", f"Automation '{rule_name}' triggered")
    link = context.get("link")
    event_engagement_id = context.get("engagement_id")

    # Build a deep link from context if not provided
    if not link:
        link = _build_resource_link(context)

    async def _can_see_engagement(uid: str) -> bool:
        """Mirror the read-side gate: admin/lead bypass, VIEW_ALL_ENGAGEMENTS
        bypass, otherwise engagement_view on this engagement."""
        if not event_engagement_id:
            return True
        try:
            user = (
                await db.execute(select(User).where(User.id == uid))
            ).scalar_one_or_none()
            if user is None:
                return False
            if user.role in (UserRole.ADMIN, UserRole.READ_ONLY_ADMIN, UserRole.TEAM_LEAD):
                return True
            if await has_global_permission(user, Permission.VIEW_ALL_ENGAGEMENTS, db):
                return True
            return await check_engagement_permission(
                uid, event_engagement_id, Permission.ENGAGEMENT_VIEW.value, db
            )
        except Exception:
            return False  # fail closed

    for uid in user_ids:
        if not await _can_see_engagement(uid):
            continue
        # Bypass the default "don't ping the actor about their own
        # action" self-suppression in two cases:
        #   1. Personal rules — always owner→self; the check would
        #      silently drop every fire.
        #   2. Manual runs via the /run endpoint — the whole point of
        #      Run is to test the rule, so an admin who's also a
        #      recipient wants to actually see the notification pop.
        # For real trigger events on org rules, the default holds:
        # the rule author doesn't get pinged about their own action.
        # The per-event mute preference is honored regardless.
        is_manual = context.get("action") == "manual"
        await create_notification(
            db=db,
            user_id=uid,
            event_type="automation",
            title=f"⚡ {rule_name}",
            message=message,
            link=link,
            actor_id=context.get("user_id"),
            engagement_id=event_engagement_id,
            skip_self_check=rule_is_personal or is_manual,
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

    # SSRF guard (GHSA-7f74-569m-w73h): reject internal/non-public targets at
    # fire time. Caught here so a stored rule cannot reach docker-internal
    # services, loopback, or cloud metadata.
    try:
        await validate_outbound_url(url)
    except OutboundURLError as exc:
        logger.warning("Webhook for rule %r rejected: %s", rule_name, exc)
        return

    method = action.get("method", "POST").upper()
    # Drop caller-controlled headers that would let the webhook carry
    # credentials or spoof its origin against an internal service.
    headers = {
        k: v for k, v in (action.get("headers") or {}).items()
        if k.lower() not in _BLOCKED_WEBHOOK_HEADERS
    }
    body_template = action.get("body_template", "")

    # Content-type-aware template substitution. The canonical use of this
    # feature is a Slack/Teams/Discord/Jira JSON webhook; an Operator-supplied
    # {{resource_name}} carrying " or \ would otherwise break out of the
    # admin's quoted string and inject sibling keys (GHSA-rvcc-9pr2-v23q).
    content_type = next(
        (v for k, v in headers.items() if k.lower() == "content-type"),
        None,
    )
    if not content_type and _looks_like_json_template(body_template, list(context.keys())):
        content_type = "application/json"

    body = body_template
    for key, val in context.items():
        placeholder = f"{{{{{key}}}}}"
        safe_val = _escape_template_value(str(val) if val is not None else "", content_type)
        body = body.replace(placeholder, safe_val)

    # If no template, send context as JSON
    if not body_template:
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

    # GHSA-f6pp-m653-9r8r #2: log scheme + host only, never the path or
    # query. Discord/Slack/Teams webhooks carry the auth secret in the URL
    # path (e.g. .../webhooks/<id>/<TOKEN>); logging the full URL at INFO
    # persisted the secret into container stdout, docker journal, and any
    # log-aggregation the operator has hooked up.
    from urllib.parse import urlparse
    try:
        parsed = urlparse(url)
        redacted_url = f"{parsed.scheme}://{parsed.netloc}/…" if parsed.netloc else "<invalid-url>"
    except Exception:
        redacted_url = "<unparseable-url>"

    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
            if method == "GET":
                await client.get(url, headers=headers)
            else:
                await client.request(method, url, headers=headers, content=body)
        logger.info(f"Webhook fired for rule '{rule_name}' → {redacted_url}")
    except Exception as e:
        logger.error(f"Webhook failed for rule '{rule_name}' ({redacted_url}): {e}")


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
    import os
    from utils.email_service import send_email

    recipients = action.get("recipients", [])
    if isinstance(recipients, str):
        recipients = [r.strip() for r in recipients.split(",") if r.strip()]

    if not recipients:
        logger.warning(f"Email action in rule '{rule_name}' has no recipients. Skipping.")
        return

    # Fire-time domain allowlist (GHSA-3ccf-qpj4-vpx8 follow-up). The
    # save-time validator on ActionSchema.recipients already enforces this,
    # but the env var can tighten after a rule was saved — re-check here so
    # a previously-saved rule whose recipient now falls outside the list
    # gets filtered rather than delivered.
    raw_allow = os.environ.get("AUTOMATION_EMAIL_DOMAIN_ALLOWLIST", "").strip()
    if raw_allow:
        allow = {d.strip().lower() for d in raw_allow.split(",") if d.strip()}
        filtered = []
        for to_email in recipients:
            try:
                domain = to_email.rsplit("@", 1)[1].lower()
            except IndexError:
                logger.warning(
                    f"Email action in rule '{rule_name}': dropping malformed "
                    f"address {to_email!r}"
                )
                continue
            if domain not in allow:
                logger.warning(
                    f"Email action in rule '{rule_name}': dropping {to_email!r} "
                    f"(domain {domain!r} not on AUTOMATION_EMAIL_DOMAIN_ALLOWLIST)"
                )
                continue
            filtered.append(to_email)
        recipients = filtered
        if not recipients:
            logger.warning(
                f"Email action in rule '{rule_name}': all recipients filtered by "
                f"AUTOMATION_EMAIL_DOMAIN_ALLOWLIST. Skipping."
            )
            return

    subject_template = action.get("subject", f"RedWire Automation: {rule_name}")
    body_template = action.get("body_template", "")

    # Template variable substitution. GHSA-m28w-p732-3rm5: keep two parallel
    # bodies — text uses raw values, HTML uses html.escape'd values — so a
    # finding title containing HTML metacharacters can't break out of the
    # <pre> wrapper. The rule author's literal HTML in body_template
    # (e.g. "<strong>finding</strong>: {{resource_name}}") is preserved
    # because we only escape the *substituted values*, not the template
    # itself.
    import html as _html
    subject = subject_template
    body_text = body_template
    body_html = body_template
    for key, val in context.items():
        placeholder = f"{{{{{key}}}}}"
        str_val = str(val) if val is not None else ""
        subject = subject.replace(placeholder, str_val)
        body_text = body_text.replace(placeholder, str_val)
        body_html = body_html.replace(placeholder, _html.escape(str_val))

    if not body_template:
        import json
        body_text = json.dumps({
            "rule": rule_name,
            "trigger": context.get("action"),
            "resource_type": context.get("resource_type"),
            "resource_name": context.get("resource_name"),
            "engagement_id": context.get("engagement_id"),
            "details": context.get("details"),
        }, indent=2)
        # The fallback JSON is entirely user-data-derived (resource_name,
        # details, etc.) — escape the whole serialized form for the HTML
        # part.
        body_html = _html.escape(body_text)

    # Wrap basic text in HTML for HTML body
    html_body = f"<pre style='font-family: monospace; padding: 16px; background: #f8f9fa; border-radius: 8px;'>{body_html}</pre>"

    try:
        for to_email in recipients:
            await send_email(db, to_email, subject, html_body, text_body=body_text)
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
    rule_is_personal = getattr(rule, "owner_user_id", None) is not None
    print(f"[AUTOMATION] Executing {len(actions)} action(s) for rule '{rule.name}' (personal={rule_is_personal})")

    for action_config in actions:
        action_type = action_config.get("type")
        executor = _ACTION_EXECUTORS.get(action_type)
        if not executor:
            print(f"[AUTOMATION] Unknown action type '{action_type}' in rule '{rule.name}'")
            continue

        try:
            if action_type == "notify_users":
                await executor(db, action_config, context, rule.name,
                               rule_is_personal=rule_is_personal)
            elif action_type in ("notify_role", "email", "add_tags"):
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

    # GHSA-jvcx-44v2-gc9m: dispatch must be tenant-aware. Match a rule iff
    # it's either global (engagement_id IS NULL, admin-curated) or scoped to
    # the engagement that raised this event. If the event has no engagement
    # context, only global rules can match — non-global rules can't fire for
    # events outside their engagement.
    #
    # Personal rules (owner_user_id set) additionally require that the event
    # was caused by the owner — filtered post-query so we don't have to
    # dispatch both branches into SQL. Owner match is on ``context.user_id``
    # (the actor of the activity).
    from sqlalchemy import or_
    event_engagement_id = context.get("engagement_id")
    event_actor_id = context.get("user_id")

    # GHSA-cjgm-6cr5-j3x2: outer try/except guards the query path only.
    # Per-rule failures are caught one level down so one rule's exception
    # can't suppress every other tenant's rules on the same event.
    try:
        if event_engagement_id:
            scope_clause = or_(
                AutomationRule.engagement_id.is_(None),
                AutomationRule.engagement_id == event_engagement_id,
            )
        else:
            scope_clause = AutomationRule.engagement_id.is_(None)
        result = await db.execute(
            select(AutomationRule).where(
                AutomationRule.trigger_type == trigger_type,
                AutomationRule.is_enabled == True,
                scope_clause,
            )
        )
        rules = result.scalars().all()
    except Exception as e:
        print(f"[AUTOMATION] ENGINE QUERY ERROR: {e}")
        logger.error(f"Automation engine query error: {e}")
        return

    # Drop personal rules whose owner didn't cause this event. Keeps
    # notifications scoped to "things I did" rather than the full org firehose.
    rules = [
        r for r in rules
        if r.owner_user_id is None or r.owner_user_id == event_actor_id
    ]

    print(f"[AUTOMATION] evaluate_rules: trigger='{trigger_type}', found {len(rules)} rule(s), context keys={list(context.keys())}")
    if context.get('status'):
        print(f"[AUTOMATION]   context status='{context.get('status')}', severity='{context.get('severity')}'")

    for rule in rules:
        try:
            conditions = rule.conditions or []

            print(f"[AUTOMATION] Evaluating rule '{rule.name}' with {len(conditions)} condition(s)")

            if not _all_conditions_match(conditions, context):
                print(f"[AUTOMATION] Rule '{rule.name}' → conditions did NOT match, skipping")
                continue

            print(f"[AUTOMATION] Rule '{rule.name}' → MATCHED! Executing actions")
            await execute_rule_actions(db, rule, context)
        except Exception as e:
            # One bad rule shouldn't suppress the others. Log with rule.id so
            # an admin can find and delete the offender.
            logger.warning(
                "Automation rule %s ('%s') failed evaluation: %s",
                rule.id, rule.name, e,
            )
            print(f"[AUTOMATION] Rule '{rule.name}' (id={rule.id}) FAILED: {e}")

    # Note: do NOT commit here — caller (create_activity_log) commits
    # after all rule evaluations complete

