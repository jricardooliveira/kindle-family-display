from datetime import date, timedelta

from app.decision.facts import fact_for


def test_each_day_has_translated_fact_with_stable_rotation():
    for index in range(35):
        day = date(2026, 1, 1) + timedelta(days=index)
        facts = [fact_for(day, language=language) for language in ("pt", "en", "de")]
        assert len({text for _, text in facts}) == 3
        assert all(category and text for category, text in facts)
        assert fact_for(day) == facts[0]


def test_data_catalog_keys_and_placeholders_have_equal_coverage():
    from string import Formatter

    from app.i18n.data import CATALOG

    assert CATALOG["pt"].keys() == CATALOG["en"].keys() == CATALOG["de"].keys()
    for key in CATALOG["pt"]:
        fields = [
            {
                field
                for _, field, _, _ in Formatter().parse(CATALOG[language][key])
                if field is not None
            }
            for language in ("pt", "en", "de")
        ]
        assert fields[0] == fields[1] == fields[2], key
