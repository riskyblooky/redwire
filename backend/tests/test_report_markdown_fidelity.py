"""Report markdown: author text in angle brackets and code survive, while
raw HTML stays inert (HTML report) / escaped (markdown export)."""

from __future__ import annotations

from types import SimpleNamespace

from utils.report_generator import HTMLReportGenerator, _markdown_from_html


def _md(text):
    gen = HTMLReportGenerator.__new__(HTMLReportGenerator)
    gen.markdown_image_map = {}
    return gen._md(text)


def test_html_report_code_and_quotes_render_once():
    out = _md("use `a<b && c>d`\n\n> quoted\n\n```\n<tag>\n```")
    assert "<code>a&lt;b &amp;&amp; c&gt;d</code>" in out
    assert "&amp;lt;" not in out
    assert "<blockquote>" in out
    assert "&lt;tag&gt;" in out


def test_html_report_raw_html_is_inert():
    for evil in ("<script>alert(1)</script>", "x <img src=x onerror=alert(1)> y",
                 "<div onclick=evil()>\nhi\n</div>", '<div markdown="1">*x*</div>'):
        out = _md(evil)
        assert "<script" not in out and "<img" not in out and "<div" not in out, out
    assert 'href="#"' in _md("[c](javascript:alert(1))")


def test_markdown_export_keeps_angle_bracket_text():
    assert _markdown_from_html("<p>use &lt;username&gt; and List&lt;String&gt;</p>") == \
        "use &lt;username> and List&lt;String>"
    assert _markdown_from_html("<p>run <code>cat &lt;file&gt;</code></p>") == "run `cat <file>`"
    assert _markdown_from_html("<pre><code>a &lt; b</code></pre>") == "```\na < b\n```"


def test_markdown_export_editor_markdown_round_trips():
    # What the editor actually stores: prose "<" as entities, code verbatim.
    src = ("User &lt;username&gt; uses List&lt;String&gt;.\n\n"
           "Run `cat <file> && echo a<b`\n\n> quoted note\n\n"
           "```\nList<String> x = <tag>;\n```")
    assert _markdown_from_html(src) == (
        "User &lt;username> uses List&lt;String>.\n\n"
        "Run `cat <file> && echo a<b`\n\n> quoted note\n\n"
        "```\nList<String> x = <tag>;\n```")


def test_markdown_export_never_emits_raw_tags():
    out = _markdown_from_html("<p>&lt;img src=x onerror=alert(1)&gt;</p><script>x</script>")
    assert "<img" not in out and "<script" not in out
    # Inert in a non-CommonMark renderer too (no backslash-escape reliance).
    import markdown
    rendered = markdown.markdown(out)
    assert "<img" not in rendered and "<script" not in rendered
