"""Deterministic daily facts in each supported display language."""

from datetime import date

from app.i18n import Language
from app.i18n.data import text

_FACT_COUNT = 35


def fact_for(day: date, language: Language = "pt") -> tuple[str, str]:
    index = day.toordinal() % _FACT_COUNT
    return text(f"fact.{index}.category", language), text(f"fact.{index}.text", language)
