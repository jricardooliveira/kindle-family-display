from datetime import UTC, datetime
from io import BytesIO

from PIL import Image

from app.contracts import DisplayDecision, DisplayLayout
from app.rendering import demo_context, render


def image_from_png(data: bytes) -> Image.Image:
    image = Image.open(BytesIO(data))
    image.load()
    return image


def test_all_screens_render_at_paperwhite_native_resolution():
    context = demo_context(datetime(2026, 10, 4, 9, tzinfo=UTC), "Europe/Lisbon")
    decision = DisplayDecision(
        layout=DisplayLayout.HERO,
        item_ids=[item.id for item in context.items if not item.is_protected][:3],
        protected_alert_ids=context.protected_alert_ids,
        reason="synthetic Paperwhite fixture",
        generated_at=context.generated_at,
        provider="rules",
    )

    for screen in ("news-weather", "family", "calendar"):
        image = image_from_png(render(screen, context, decision, 1236, 1648))

        assert image.mode == "L"
        assert image.size == (1236, 1648)
        assert image.getextrema()[0] < 255


def test_paperwhite_native_canvas_rotates_to_landscape_dimensions():
    context = demo_context(datetime(2026, 10, 4, 9, tzinfo=UTC), "Europe/Lisbon")
    decision = DisplayDecision(
        layout=DisplayLayout.HERO,
        item_ids=[item.id for item in context.items if not item.is_protected][:3],
        protected_alert_ids=context.protected_alert_ids,
        reason="synthetic Paperwhite rotation fixture",
        generated_at=context.generated_at,
        provider="rules",
    )

    image = image_from_png(render("news-weather", context, decision, 1236, 1648, rotation=90))

    assert image.mode == "L"
    assert image.size == (1648, 1236)
