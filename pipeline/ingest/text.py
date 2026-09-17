"""Text cleanup shared by the source clients."""

from __future__ import annotations

import html
import re

_LIST_ITEM = re.compile(r"<li\b[^>]*>", re.IGNORECASE)
_BLOCK_END = re.compile(r"<br\s*/?>|</(?:p|div|h[1-6]|ul|ol|tr|section|article)>", re.IGNORECASE)
_TAG = re.compile(r"<[^>]+>")
_INLINE_SPACE = re.compile(r"[ \t\r\f\v ]+")
_ORPHAN_BULLET = re.compile(r"^-\n+", re.MULTILINE)
_EXTRA_BLANK_LINES = re.compile(r"\n{3,}")

_NON_WORD = re.compile(r"[^\w]+")
_LEGAL_SUFFIXES = frozenset(
    "ab ag as bv co corp corporation gmbh inc incorporated limited llc ltd nv oy plc pty sa sas "
    "spa srl".split()
)


def html_to_text(markup: str, *, escaped: bool = False) -> str:
    """Plain text from job-description HTML, keeping paragraph and list-item breaks.

    Set `escaped` for HTML that arrives entity-encoded (Greenhouse sends `&lt;p&gt;`).
    Other sources must not set it, or a literal "&lt;5 years" would be read as a tag.
    """
    if escaped:
        markup = html.unescape(markup)
    text = _LIST_ITEM.sub("\n- ", markup)
    text = _BLOCK_END.sub("\n", text)
    text = html.unescape(_TAG.sub("", text))
    text = _INLINE_SPACE.sub(" ", text)
    text = "\n".join(line.strip() for line in text.split("\n"))
    text = _ORPHAN_BULLET.sub("- ", text)
    return _EXTRA_BLANK_LINES.sub("\n\n", text).strip()


def normalize_company(name: str) -> str:
    """Lowercase company name without punctuation or trailing legal suffixes.

    "Acme, Inc." and "ACME" both become "acme".
    """
    tokens = _NON_WORD.sub(" ", name.lower()).split()
    while len(tokens) > 1 and tokens[-1] in _LEGAL_SUFFIXES:
        tokens.pop()
    return " ".join(tokens)
