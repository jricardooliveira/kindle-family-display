"""Scaled grayscale drawing primitives for the 800×600 landscape design."""

from __future__ import annotations

from dataclasses import dataclass, replace
from functools import lru_cache
from io import BytesIO
from math import ceil
from pathlib import Path

import segno
from PIL import Image, ImageDraw, ImageFont, ImageOps

DESIGN_WIDTH = 800
DESIGN_HEIGHT = 600
# The handoff tokens are #0c0c0c on #f1f0ec; a 16-level panel shows that paper as a grey
# tint, so the device output uses the panel's own black and white.
INK = 0
PAPER = 255

_FONT_DIR = Path(__file__).parent / "fonts"
_FALLBACK_FONTS = {
    False: (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
    ),
    True: (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    ),
}
_SUPERSAMPLE = 4
_CLOUD = "cloud"
_ICONS = {"sun", "cloud", "rain", "wind", "storm", "sunrise"}
BADGE_SHAPES = ("square-filled", "circle-outline", "circle-filled", "square-outline")


@dataclass(frozen=True)
class Style:
    """Text style in design pixels; `display` selects Bricolage Grotesque."""

    size: float
    weight: int = 400
    display: bool = False
    leading: float = 1.2
    tracking: float = 0.0
    upper: bool = False

    def sized(self, size: float) -> Style:
        return replace(self, size=size)

    @property
    def line_height(self) -> float:
        return self.size * self.leading


@lru_cache(maxsize=128)
def _load_font(display: bool, pixels: int, weight: int, optical: int) -> ImageFont.FreeTypeFont:
    name = "BricolageGrotesque.ttf" if display else "InstrumentSans.ttf"
    try:
        font = ImageFont.truetype(str(_FONT_DIR / name), pixels)
        wanted = {"Weight": weight, "Optical size": optical, "Width": 100}
        axes = []
        for axis in font.get_variation_axes():
            raw = axis["name"]
            label = raw.decode() if isinstance(raw, bytes) else str(raw)
            value = float(wanted.get(label) or axis["default"] or 0)
            axes.append(max(float(axis["minimum"] or 0), min(float(axis["maximum"] or 0), value)))
        font.set_variation_by_axes(axes)
        return font
    except OSError:
        for path in _FALLBACK_FONTS[weight >= 600]:
            if Path(path).is_file():
                return ImageFont.truetype(path, pixels)
    raise RuntimeError("No supported font found; bundled fonts are missing")


class Canvas:
    """A grayscale page addressed in design pixels and scaled to the device size."""

    def __init__(self, width: int, height: int, *, inverted: bool = False) -> None:
        self.scale = min(width / DESIGN_WIDTH, height / DESIGN_HEIGHT)
        self.width = width / self.scale
        self.height = height / self.scale
        self.ink, self.paper = (PAPER, INK) if inverted else (INK, PAPER)
        self.image = Image.new("L", (width, height), self.paper)
        self._draw = ImageDraw.Draw(self.image)

    def _px(self, value: float) -> int:
        return round(value * self.scale)

    def _font(self, style: Style) -> ImageFont.FreeTypeFont:
        optical = round(max(12, min(96, style.size)))
        return _load_font(style.display, max(1, self._px(style.size)), style.weight, optical)

    def _shown(self, text: str, style: Style) -> str:
        return text.upper() if style.upper else text

    def measure(self, text: str, style: Style) -> float:
        shown = self._shown(text, style)
        length = self._font(style).getlength(shown)
        return length / self.scale + style.tracking * style.size * len(shown)

    def baseline(self, top: float, style: Style) -> float:
        ascent, descent = self._font(style).getmetrics()
        return top + (style.line_height - (ascent + descent) / self.scale) / 2 + ascent / self.scale

    def line(
        self,
        x: float,
        top: float,
        text: str,
        style: Style,
        *,
        anchor: str = "l",
        baseline: float | None = None,
        fill: int | None = None,
    ) -> float:
        """Draw one line in a CSS-like line box starting at `top`; return its width."""
        shown = self._shown(text, style)
        font = self._font(style)
        width = self.measure(text, style)
        if anchor == "r":
            x -= width
        elif anchor == "m":
            x -= width / 2
        y = self._px(self.baseline(top, style) if baseline is None else baseline)
        colour = self.ink if fill is None else fill
        if not style.tracking:
            self._draw.text((self._px(x), y), shown, font=font, fill=colour, anchor="ls")
            return width
        tracking = style.tracking * style.size * self.scale
        origin = x * self.scale
        for index, character in enumerate(shown):
            offset = font.getlength(shown[:index]) + index * tracking
            self._draw.text(
                (round(origin + offset), y), character, font=font, fill=colour, anchor="ls"
            )
        return width

    def wrap(self, text: str, style: Style, max_width: float) -> list[str]:
        """Wrap words and split overlong tokens so they never run off the page."""
        lines: list[str] = []
        for paragraph in text.splitlines() or [text]:
            current = ""
            for word in paragraph.split():
                for part in self._split_word(word, style, max_width):
                    candidate = f"{current} {part}".strip()
                    if current and self.measure(candidate, style) > max_width:
                        lines.append(current)
                        current = part
                    else:
                        current = candidate
            if current:
                lines.append(current)
        return lines or [""]

    def _split_word(self, word: str, style: Style, max_width: float) -> list[str]:
        if self.measure(word, style) <= max_width:
            return [word]
        parts: list[str] = []
        rest = word
        while rest:
            low, high = 1, len(rest)
            while low < high:
                middle = (low + high + 1) // 2
                if self.measure(rest[:middle], style) <= max_width:
                    low = middle
                else:
                    high = middle - 1
            parts.append(rest[:low])
            rest = rest[low:]
        return parts

    def truncate(self, text: str, style: Style, max_width: float) -> str:
        if self.measure(text, style) <= max_width:
            return text
        low, high = 0, len(text)
        while low < high:
            middle = (low + high + 1) // 2
            if self.measure(text[:middle].rstrip() + "…", style) <= max_width:
                low = middle
            else:
                high = middle - 1
        return text[:low].rstrip() + "…"

    def clamp(self, text: str, style: Style, max_width: float, max_lines: int) -> list[str]:
        """Wrap to at most `max_lines`, marking dropped text with an ellipsis."""
        lines = self.wrap(text, style, max_width)
        if len(lines) <= max_lines:
            return lines
        kept = lines[: max(1, max_lines)]
        kept[-1] = self.truncate(kept[-1] + "…", style, max_width)
        return kept

    def fit(
        self,
        text: str,
        style: Style,
        sizes: tuple[float, ...],
        max_width: float,
        max_height: float,
        max_lines: int,
    ) -> tuple[Style, list[str]]:
        """Pick the largest size whose unbroken words fit the box; clamp at the smallest."""
        words = text.split()
        for size in sizes:
            candidate = style.sized(size)
            if any(self.measure(word, candidate) > max_width for word in words):
                continue
            lines = self.wrap(text, candidate, max_width)
            if len(lines) <= max_lines and len(lines) * candidate.line_height <= max_height:
                return candidate, lines
        smallest = style.sized(sizes[-1])
        allowed = max(1, min(max_lines, int(max_height // smallest.line_height)))
        return smallest, self.clamp(text, smallest, max_width, allowed)

    def lines(self, x: float, top: float, lines: list[str], style: Style) -> float:
        """Draw already wrapped lines and return the bottom of the block."""
        for index, text in enumerate(lines):
            self.line(x, top + index * style.line_height, text, style)
        return top + len(lines) * style.line_height

    def block(
        self, x: float, top: float, text: str, style: Style, max_width: float, max_bottom: float
    ) -> float:
        """Draw wrapped text that stops at `max_bottom`; return the bottom of the block."""
        allowed = int((max_bottom - top) // style.line_height)
        if allowed < 1:
            return top
        return self.lines(x, top, self.clamp(text, style, max_width, allowed), style)

    def rect(self, x0: float, y0: float, x1: float, y1: float, fill: int | None = None) -> None:
        left, top = self._px(x0), self._px(y0)
        right, bottom = max(left, self._px(x1) - 1), max(top, self._px(y1) - 1)
        self._draw.rectangle((left, top, right, bottom), fill=self.ink if fill is None else fill)

    def rule(self, x0: float, y: float, x1: float, thickness: float) -> None:
        top = self._px(y)
        height = max(1, self._px(thickness))
        self._draw.rectangle(
            (self._px(x0), top, max(self._px(x0), self._px(x1) - 1), top + height - 1),
            fill=self.ink,
        )

    def vrule(self, x: float, y0: float, y1: float, thickness: float) -> None:
        left = self._px(x)
        width = max(1, self._px(thickness))
        self._draw.rectangle(
            (left, self._px(y0), left + width - 1, max(self._px(y0), self._px(y1) - 1)),
            fill=self.ink,
        )

    def _stamp(self, mask: Image.Image, x: float, top: float, size: float) -> None:
        pixels = max(1, self._px(size))
        small = mask.resize((pixels, pixels), Image.Resampling.LANCZOS)
        self.image.paste(self.ink, (self._px(x), self._px(top)), small)

    def icon(self, name: str, x: float, top: float, size: float) -> None:
        """Draw a 64×64 weather glyph: 4 px round strokes, cloud filled with ink."""
        unit = max(1, ceil(self._px(size) * _SUPERSAMPLE / 64))
        self._stamp(_icon_mask(name if name in _ICONS else _CLOUD, unit), x, top, size)

    def badge(self, x: float, top: float, initial: str, shape: str, size: float = 32) -> None:
        """Draw a person badge: an initial inside one of four fixed shapes."""
        self._stamp(_badge_mask(shape), x, top, size)
        filled = shape.endswith("filled")
        style = Style(19 * size / 32, 700, display=True, leading=1.0)
        font = self._font(style)
        centre = (self._px(x + size / 2), self._px(top + size / 2))
        colour = self.paper if filled else self.ink
        self._draw.text(centre, initial.upper(), font=font, fill=colour, anchor="mm")

    def square(self, x: float, top: float, size: float, *, filled: bool) -> None:
        left, upper = self._px(x), self._px(top)
        side = max(3, self._px(size))
        box = (left, upper, left + side - 1, upper + side - 1)
        if filled:
            self._draw.rectangle(box, fill=self.ink)
        else:
            self._draw.rectangle(box, outline=self.ink, width=max(1, self._px(2)))

    def qr(self, url: str, right: float, bottom: float, size: float) -> float:
        """Draw a level-M QR anchored bottom-right; return the side used (0 if skipped)."""
        try:
            matrix = segno.make(url, error="m", micro=False, boost_error=False).matrix
        except (ValueError, segno.DataOverflowError):
            return 0.0
        modules = len(matrix) + 8  # four quiet modules on each side
        unit = self._px(size) // modules
        if unit < 3:
            # Keep codes scannable on low-resolution output by letting the box grow.
            unit = min(3, self._px(size * 1.6) // modules)
        if unit < 2:
            return 0.0
        side = unit * modules
        left, top = self._px(right) - side, self._px(bottom) - side
        self._draw.rectangle((left, top, left + side - 1, top + side - 1), fill=PAPER)
        for row_index, row in enumerate(matrix):
            for column_index, dark in enumerate(row):
                if dark:
                    x = left + (column_index + 4) * unit
                    y = top + (row_index + 4) * unit
                    self._draw.rectangle((x, y, x + unit - 1, y + unit - 1), fill=INK)
        return side / self.scale

    def photo(self, path: str) -> bool:
        """Fill the page with a photo dithered to four grey levels; False if unreadable."""
        try:
            with Image.open(path) as source:
                source.draft("L", self.image.size)
                picture = ImageOps.exif_transpose(source).convert("L")
        except (OSError, ValueError, Image.DecompressionBombError):
            return False
        picture = ImageOps.fit(picture, self.image.size, Image.Resampling.LANCZOS)
        picture = ImageOps.autocontrast(picture, cutoff=1)
        palette = Image.new("P", (1, 1))
        palette.putpalette([level for grey in (0, 85, 170, 255) for level in (grey,) * 3])
        dithered = picture.convert("RGB").quantize(
            palette=palette, dither=Image.Dither.FLOYDSTEINBERG
        )
        self.image.paste(dithered.convert("L"))
        return True

    def png(self, rotation: int = 0) -> bytes:
        image = self.image
        if rotation:
            image = image.transpose(
                {
                    90: Image.Transpose.ROTATE_270,
                    180: Image.Transpose.ROTATE_180,
                    270: Image.Transpose.ROTATE_90,
                }[rotation]
            )
        output = BytesIO()
        image.save(output, format="PNG", optimize=True)
        return output.getvalue()


class _Pen:
    """Round-capped strokes in the icons' 64×64 view box."""

    def __init__(self, unit: int) -> None:
        self.unit = unit
        self.image = Image.new("L", (64 * unit, 64 * unit), 0)
        self.draw = ImageDraw.Draw(self.image)

    def dot(self, x: float, y: float, radius: float) -> None:
        u = self.unit
        self.draw.ellipse(
            ((x - radius) * u, (y - radius) * u, (x + radius) * u, (y + radius) * u), fill=255
        )

    def stroke(self, *points: tuple[float, float]) -> None:
        u = self.unit
        self.draw.line([(x * u, y * u) for x, y in points], fill=255, width=4 * u, joint="curve")
        for x, y in points:
            self.dot(x, y, 2)

    def arc(self, cx: float, cy: float, radius: float, start: float, end: float) -> None:
        u = self.unit
        outer = radius + 2
        box = ((cx - outer) * u, (cy - outer) * u, (cx + outer) * u, (cy + outer) * u)
        self.draw.arc(box, start, end, fill=255, width=4 * u)

    def cloud(self) -> None:
        u = self.unit
        self.dot(22, 30, 11)
        self.dot(36, 22, 14)
        self.dot(48, 32, 9)
        self.draw.rectangle((22 * u, 30 * u, 48 * u, 41 * u), fill=255)


@lru_cache(maxsize=32)
def _icon_mask(name: str, unit: int) -> Image.Image:
    pen = _Pen(unit)
    if name == "sun":
        pen.arc(32, 32, 11, 0, 360)
        for ray in (
            ((51.0, 32.0), (59.0, 32.0)),
            ((45.4, 45.4), (51.1, 51.1)),
            ((32.0, 51.0), (32.0, 59.0)),
            ((18.6, 45.4), (12.9, 51.1)),
            ((13.0, 32.0), (5.0, 32.0)),
            ((18.6, 18.6), (12.9, 12.9)),
            ((32.0, 13.0), (32.0, 5.0)),
            ((45.4, 18.6), (51.1, 12.9)),
        ):
            pen.stroke(*ray)
    elif name == "sunrise":
        pen.arc(32, 44, 18, 180, 360)
        pen.stroke((6, 44), (58, 44))
        pen.stroke((32, 10), (32, 18))
        pen.stroke((12, 20), (17, 25))
        pen.stroke((52, 20), (47, 25))
        pen.stroke((20, 54), (44, 54))
    elif name == "wind":
        pen.stroke((6, 22), (40, 22))
        pen.arc(40, 14, 8, 180, 450)
        pen.dot(32, 14, 2)
        pen.stroke((6, 34), (52, 34))
        pen.arc(52, 42, 8, 270, 540)
        pen.dot(44, 42, 2)
        pen.stroke((6, 46), (28, 46))
    else:
        pen.cloud()
        if name == "rain":
            for x in (20, 32, 44):
                pen.stroke((x, 47), (x - 4, 57))
        elif name == "storm":
            pen.stroke((34, 42), (26, 52), (36, 52), (28, 62))
    return pen.image


@lru_cache(maxsize=8)
def _badge_mask(shape: str) -> Image.Image:
    side = 32 * _SUPERSAMPLE * 2
    stroke = round(2.5 * _SUPERSAMPLE * 2)
    image = Image.new("L", (side, side), 0)
    draw = ImageDraw.Draw(image)
    box = (0, 0, side - 1, side - 1)
    figure = draw.ellipse if shape.startswith("circle") else draw.rectangle
    if shape.endswith("filled"):
        figure(box, fill=255)
    else:
        figure(box, outline=255, width=stroke)
    return image
