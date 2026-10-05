"""Small, dependency-free text cleanup helpers for feed content."""

from __future__ import annotations

import unicodedata
from html.parser import HTMLParser

_HIDDEN_TAGS = {"script", "style"}
_BLOCK_TAGS = {
    "address",
    "article",
    "blockquote",
    "br",
    "dd",
    "div",
    "dl",
    "dt",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "li",
    "ol",
    "p",
    "pre",
    "section",
    "table",
    "td",
    "th",
    "tr",
    "ul",
}


class _PlainTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.hidden: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        if tag in _HIDDEN_TAGS:
            self.hidden.append(tag)
        elif not self.hidden and tag in _BLOCK_TAGS:
            self.parts.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag in _HIDDEN_TAGS and tag in self.hidden:
            self.hidden.remove(tag)
        elif not self.hidden and tag in _BLOCK_TAGS:
            self.parts.append(" ")

    def handle_data(self, data: str) -> None:
        if not self.hidden:
            self.parts.append(data)


def plain_text(value: object, *, max_length: int) -> str:
    """Decode entities, remove markup/control characters and bound the result."""
    if not isinstance(value, str) or max_length < 1:
        return ""
    parser = _PlainTextParser()
    parser.feed(value)
    parser.close()
    text = unicodedata.normalize("NFKC", " ".join(parser.parts))
    text = "".join(
        character
        for character in text
        if unicodedata.category(character) != "Cc" or character in "\t\n\r"
    )
    return " ".join(text.split())[:max_length].strip()
