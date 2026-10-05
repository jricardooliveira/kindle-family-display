"""Explicit, locale-independent translation helpers for the fixed display."""

from typing import Literal

Language = Literal["pt", "en", "de"]
Country = Literal["PT", "GB", "DE"]


def translate(
    catalog: dict[str, dict[str, str]],
    key: str,
    language: Language = "pt",
    **values: object,
) -> str:
    """Resolve a complete catalog entry; missing translations fail visibly in tests."""
    return catalog[language][key].format(**values)


def format_number(value: float | None, language: Language = "pt") -> str:
    """Format compact display numbers with the locale's decimal separator."""
    if value is None:
        return "—"
    result = f"{value:g}"
    return result.replace(".", ",") if language in ("pt", "de") else result
