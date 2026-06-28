"""Webhook chat-token defang regressions.

GHSA-rvcc-9pr2-v23q shipped JSON-string escaping so a low-privileged
user can't break out of the admin's body template and inject sibling
keys. The follow-up here closes the second half of the surface:
receiver-rendered tokens (Slack `<!channel>`, `<@U…>`, Teams `<at>…`,
`<url|text>` mrkdwn hyperlinks) are valid string content and survive
any JSON escape — once delivered, the receiver still renders the
broadcast / phishing link under the integration's identity.

These tests pin the defang contract:

  1. JSON-body substitutions defang the named tokens.
  2. Defang preserves the textual signal (no information loss for the
     human reader), only the rendering side-effect is removed.
  3. Non-JSON content types (XML, urlencoded, plain) are NOT defanged
     because their receivers don't render these tokens.
  4. Strings without `<` short-circuit (defang is a hot-path helper —
     this keeps the common case allocation-free).
"""

from __future__ import annotations

import json

import pytest

from utils.automation_engine import (
    _defang_chat_tokens,
    _escape_template_value,
)


# ── _defang_chat_tokens: per-token coverage ──────────────────────────


class TestSlackBroadcasts:
    """`<!channel>` / `<!here>` / `<!everyone>` pings the entire room
    under the bot's identity — the highest-impact token an attacker
    can smuggle through a finding title."""

    @pytest.mark.parametrize("token,expected", [
        ("<!channel>", "[@channel]"),
        ("<!here>", "[@here]"),
        ("<!everyone>", "[@everyone]"),
        ("<!CHANNEL>", "[@channel]"),  # IGNORECASE — Slack accepts mixed case
        ("<!Here>", "[@here]"),
    ])
    def test_each_broadcast_token_defanged(self, token, expected):
        assert _defang_chat_tokens(token) == expected

    def test_embedded_in_text(self):
        assert _defang_chat_tokens(
            "Finding: SQLi at /login <!channel> urgent"
        ) == "Finding: SQLi at /login [@channel] urgent"


class TestSlackMentions:
    """User / channel / subteam mentions ping the named target.
    Defang reads as a literal so the recipient still sees that a
    mention was attempted, just without the ping side-effect."""

    def test_user_mention_id_only(self):
        assert _defang_chat_tokens("hi <@U12345ABC>") == "hi [user mention]"

    def test_user_mention_with_fallback_label(self):
        # Slack lets `<@U123|jdoe>` carry a display name — still pings.
        assert _defang_chat_tokens("hi <@U12345ABC|jdoe>") == "hi [user mention]"

    def test_workspace_user_mention(self):
        # `W` prefix = Enterprise Grid user id.
        assert _defang_chat_tokens("hi <@W9999XYZ>") == "hi [user mention]"

    def test_channel_mention_no_label(self):
        assert _defang_chat_tokens("see <#C12345>") == "see [channel mention]"

    def test_channel_mention_with_label(self):
        # Label is preserved in the readable defang so the link target is auditable.
        assert _defang_chat_tokens("see <#C12345|general>") == "see [channel mention: general]"

    def test_group_mention_with_handle(self):
        # `<!subteam^S123|@oncall>` pings the @oncall user group.
        out = _defang_chat_tokens("alert <!subteam^S12345|@oncall>")
        assert out == "alert [group mention: @oncall]"

    def test_group_mention_id_only(self):
        out = _defang_chat_tokens("alert <!subteam^S12345>")
        assert out == "alert [group mention]"


class TestMrkdwnLinks:
    """`<https://x|click here>` renders as a clickable hyperlink in
    Slack — the phishing primitive. Defang preserves both URL and
    label so the recipient can still evaluate the link, just not
    auto-click on a misleading label."""

    def test_basic_link(self):
        assert _defang_chat_tokens("see <https://evil.com|safe site>") == (
            "see safe site (https://evil.com)"
        )

    def test_http_scheme(self):
        assert _defang_chat_tokens("<http://x.test|click>") == "click (http://x.test)"

    def test_only_http_https_match(self):
        # A `<foo|bar>` without an http(s) scheme isn't a mrkdwn link.
        assert _defang_chat_tokens("<arbitrary|stuff>") == "<arbitrary|stuff>"


class TestTeamsAt:
    """Teams `<at>` tags ping the named user inside an adaptive
    card. Same readability-preserving defang."""

    def test_simple_at(self):
        assert _defang_chat_tokens("<at>Alice</at>") == "[mention: Alice]"

    def test_at_with_id_attr(self):
        # Teams' canonical form carries an `id` attr that links to the entity ref.
        out = _defang_chat_tokens('hi <at id="0">Alice Smith</at>')
        assert out == "hi [mention: Alice Smith]"

    def test_at_case_insensitive(self):
        assert _defang_chat_tokens("<AT>Bob</AT>") == "[mention: Bob]"

    def test_empty_at_falls_back(self):
        assert _defang_chat_tokens("<at></at>") == "[mention]"


# ── _defang_chat_tokens: false-positive avoidance ───────────────────


class TestFalsePositiveAvoidance:
    """Conservative-by-design: anything that doesn't match a known
    rendering token must pass through untouched, even if it contains
    `<` or `>`."""

    def test_literal_less_than(self):
        # `2 < 3` — bare math-style comparison, no rendering side effect.
        assert _defang_chat_tokens("count 2 < 3 items") == "count 2 < 3 items"

    def test_html_passthrough(self):
        # We don't try to be an HTML sanitiser — Slack/Teams renders this as text,
        # and downstream JSON escaping is what protects the receiver from XSS.
        assert _defang_chat_tokens("<script>alert(1)</script>") == "<script>alert(1)</script>"

    def test_arbitrary_tag(self):
        assert _defang_chat_tokens("<custom>data</custom>") == "<custom>data</custom>"

    def test_empty_returns_empty(self):
        assert _defang_chat_tokens("") == ""

    def test_no_angle_brackets_short_circuit(self):
        # Hot-path optimisation: most substituted values have no `<` at all
        # and should return without scanning the regex set.
        s = "a normal finding title with no tokens"
        assert _defang_chat_tokens(s) is s  # exact-object identity


# ── _escape_template_value integration ───────────────────────────────


class TestEscapeDefangIntegration:
    """Defang fires only inside the JSON / +json content-type branches.
    XML / urlencoded / plain receivers don't render Slack tokens, so
    leaving the bytes alone preserves intent without risk."""

    def test_json_body_defangs_broadcast(self):
        out = _escape_template_value("urgent <!channel> now", "application/json")
        # Result is a JSON-string body fragment (unwrapped) — quotes escaped, defanged
        # token now reads as [@channel].
        assert out == "urgent [@channel] now"

    def test_json_body_defangs_mention(self):
        out = _escape_template_value("hi <@U123>", "application/json")
        assert out == "hi [user mention]"

    def test_json_body_defangs_mrkdwn_link(self):
        out = _escape_template_value("<https://x.test|click>", "application/json")
        assert out == "click (https://x.test)"

    def test_vendor_json_subtype_also_defanged(self):
        # `application/vnd.slack+json` and similar must defang too.
        out = _escape_template_value("<!here>", "application/vnd.slack+json")
        assert out == "[@here]"

    def test_xml_body_NOT_defanged(self):
        # XML receivers don't render Slack mrkdwn; the XML escape already
        # neutralises `<` → `&lt;` so the token can't render anywhere downstream.
        out = _escape_template_value("<!channel>", "application/xml")
        assert "&lt;!channel&gt;" in out

    def test_urlencoded_body_NOT_defanged(self):
        out = _escape_template_value("<!channel>", "application/x-www-form-urlencoded")
        assert out == "%3C%21channel%3E"

    def test_plain_text_NOT_defanged(self):
        # No content type → pass-through. Slack webhooks won't accept a
        # text/plain body anyway; this branch is for generic HTTP webhooks.
        out = _escape_template_value("<!channel>", "text/plain")
        assert out == "<!channel>"

    def test_json_escape_still_applies(self):
        # Defang doesn't replace the JSON escape — `"` in the value must
        # still get escaped to keep the structural breakout closed.
        out = _escape_template_value('say "hi" <!channel>', "application/json")
        assert out == r'say \"hi\" [@channel]'

    def test_json_body_embedded_in_template(self):
        # End-to-end shape: an admin's Slack template + an attacker-supplied value.
        template = '{"text":"New finding: {{resource_name}}"}'
        attacker = "<!channel> pwned"
        safe_val = _escape_template_value(attacker, "application/json")
        body = template.replace("{{resource_name}}", safe_val)
        # The webhook body is still valid JSON and the broadcast token is gone.
        parsed = json.loads(body)
        assert parsed["text"] == "New finding: [@channel] pwned"
