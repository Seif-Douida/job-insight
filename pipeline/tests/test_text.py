from __future__ import annotations

from pipeline.ingest.text import html_to_text, normalize_company


def test_html_to_text_decodes_escaped_markup() -> None:
    markup = (
        "&lt;h2&gt;About&lt;/h2&gt;&lt;p&gt;We build &amp;amp; ship.&lt;/p&gt;"
        "&lt;ul&gt;&lt;li&gt;Python&lt;/li&gt;&lt;li&gt;SQL&lt;/li&gt;&lt;/ul&gt;"
    )
    assert html_to_text(markup, escaped=True) == "About\nWe build & ship.\n\n- Python\n- SQL"


def test_html_to_text_keeps_literal_angle_brackets_in_plain_html() -> None:
    assert html_to_text("<p>R&amp;D, &lt;5 years</p>") == "R&D, <5 years"


def test_html_to_text_joins_bullets_split_across_paragraph_tags() -> None:
    markup = "<div><li>\n<p>Build pipelines</p>\n</li><li><p>Ship</p></li></div>"
    assert html_to_text(markup) == "- Build pipelines\n\n- Ship"


def test_html_to_text_collapses_whitespace() -> None:
    assert html_to_text("<p>a&nbsp;&nbsp; b</p><p></p><p></p><p>c</p>") == "a b\n\nc"


def test_normalize_company_drops_case_punctuation_and_legal_suffix() -> None:
    assert normalize_company("Acme, Inc.") == normalize_company("ACME") == "acme"
    assert normalize_company("Bayut | dubizzle") == "bayut dubizzle"


def test_normalize_company_keeps_a_name_that_is_only_a_suffix() -> None:
    assert normalize_company("AS") == "as"
