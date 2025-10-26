"""Halftone and dithering utilities for Dotzation."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Callable, Dict, Iterable, Optional

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap


@dataclass(frozen=True)
class HalftoneMethod:
    """Container for halftone method metadata."""

    name: str
    apply: Callable[[Image.Image, int], Image.Image]
    description: str


def load_image(path: str) -> Image.Image:
    """Load an image from *path* into an RGB Pillow image."""
    image = Image.open(path)
    return image.convert("RGB")


def save_image(image: Image.Image, path: str) -> None:
    """Persist the Pillow *image* to *path*."""
    image.save(path)


def pil_to_qimage(image: Image.Image) -> QImage:
    """Convert a Pillow image to a ``QImage`` suitable for Qt widgets."""
    if image.mode != "RGBA":
        qt_image = image.convert("RGBA")
    else:
        qt_image = image
    data = qt_image.tobytes("raw", "RGBA")
    qimage = QImage(
        data,
        qt_image.width,
        qt_image.height,
        qt_image.width * 4,
        QImage.Format.Format_RGBA8888,
    )
    return qimage.copy()


def pil_to_qpixmap(image: Image.Image) -> QPixmap:
    """Convert a Pillow image to a ``QPixmap`` for QLabel previews."""
    return QPixmap.fromImage(pil_to_qimage(image))


def apply_identity(image: Image.Image, _: int) -> Image.Image:
    """Return the original image without any processing."""
    return image.copy()


def apply_grayscale(image: Image.Image, _: int) -> Image.Image:
    """Convert the image to grayscale."""
    return ImageOps.grayscale(image).convert("RGB")


def apply_floyd_steinberg(image: Image.Image, _: int) -> Image.Image:
    """Apply Pillow's Floyd-Steinberg dithering."""
    bw = image.convert("1", dither=Image.FLOYDSTEINBERG)
    return bw.convert("RGB")


def apply_ordered_dither(image: Image.Image, _: int) -> Image.Image:
    """Apply an ordered (Bayer) dithering effect."""
    return image.convert("L").convert("1", dither=Image.Dither.ORDERED).convert("RGB")


def apply_circular_halftone(image: Image.Image, dot_size: int) -> Image.Image:
    """Render the image as a circular halftone using the supplied dot size."""
    grayscale = ImageOps.grayscale(image)
    width, height = grayscale.size
    dot_size = max(2, dot_size)
    output = Image.new("L", (width, height), color=255)
    draw = ImageDraw.Draw(output)

    for top in range(0, height, dot_size):
        for left in range(0, width, dot_size):
            box = (left, top, left + dot_size, top + dot_size)
            tile = grayscale.crop(box)
            histogram = tile.histogram()
            total_pixels = sum(histogram)
            if total_pixels == 0:
                continue
            brightness = sum(i * count for i, count in enumerate(histogram)) / total_pixels
            darkness = 1.0 - brightness / 255.0
            radius = (dot_size / 2.0) * darkness
            center_x = left + dot_size / 2.0
            center_y = top + dot_size / 2.0
            draw.ellipse(
                (
                    center_x - radius,
                    center_y - radius,
                    center_x + radius,
                    center_y + radius,
                ),
                fill=0,
            )

    return output.convert("RGB")


DEFAULT_ASCII_CHARSET = " .:-=+*#%@"
_ASCII_FONT = ImageFont.load_default()
_ASCII_CHAR_BBOX = _ASCII_FONT.getbbox("M")
_ASCII_CHAR_WIDTH = max(_ASCII_CHAR_BBOX[2] - _ASCII_CHAR_BBOX[0], 1)
_ASCII_CHAR_HEIGHT = max(_ASCII_CHAR_BBOX[3] - _ASCII_CHAR_BBOX[1], 1)
DEFAULT_ASCII_ASPECT = _ASCII_CHAR_HEIGHT / _ASCII_CHAR_WIDTH if _ASCII_CHAR_WIDTH else 1.0


def _tile_brightness(tile: Image.Image) -> float:
    """Return the average brightness of ``tile`` on a 0-255 scale."""
    histogram = tile.histogram()
    total_pixels = sum(histogram)
    if total_pixels == 0:
        return 255.0
    return sum(i * count for i, count in enumerate(histogram)) / total_pixels


@lru_cache(maxsize=64)
def _glyph_tiles(characters_key: tuple[str, ...]) -> tuple[int, int, Dict[str, Image.Image]]:
    """Return cached glyph images sized to a consistent cell."""
    if not characters_key:
        unique_chars: list[str] = [" "]
    else:
        # Preserve order while deduplicating
        seen: Dict[str, None] = {}
        for char in characters_key:
            if char not in seen:
                seen[char] = None
        unique_chars = list(seen.keys())
        if not unique_chars:
            unique_chars = [" "]

    max_width = 0
    max_height = 0
    for char in unique_chars:
        bbox = _ASCII_FONT.getbbox(char)
        if bbox is None:
            continue
        left, top, right, bottom = bbox
        width = max(0, right - left)
        height = max(0, bottom - top)
        max_width = max(max_width, width)
        max_height = max(max_height, height)

    if max_width == 0:
        max_width = _ASCII_CHAR_WIDTH
    if max_height == 0:
        max_height = _ASCII_CHAR_HEIGHT

    tiles: Dict[str, Image.Image] = {}
    blank_tile = Image.new("L", (max_width, max_height), color=255)

    for char in unique_chars:
        tile = blank_tile.copy()
        bbox = _ASCII_FONT.getbbox(char)
        if bbox is not None:
            left, top, right, bottom = bbox
            width = right - left
            height = bottom - top
            offset_x = (max_width - width) // 2 - left
            offset_y = (max_height - height) // 2 - top
            draw = ImageDraw.Draw(tile)
            draw.text((offset_x, offset_y), char, fill=0, font=_ASCII_FONT)
        tiles[char] = tile

    tiles.setdefault(" ", blank_tile)
    return max_width, max_height, tiles


def _ascii_geometry(
    dot_size: int, charset: str, cell_aspect: Optional[float]
) -> tuple[int, int, int, Dict[str, Image.Image]]:
    glyph_key = tuple(dict.fromkeys(charset))
    glyph_cell_width, glyph_cell_height, glyphs = _glyph_tiles(glyph_key)
    if glyph_cell_width == 0:
        glyph_cell_width = _ASCII_CHAR_WIDTH or 1
    if glyph_cell_height == 0:
        glyph_cell_height = _ASCII_CHAR_HEIGHT or 1

    if cell_aspect is None:
        if glyph_cell_width == 0:
            aspect = DEFAULT_ASCII_ASPECT
        else:
            aspect = glyph_cell_height / glyph_cell_width
    else:
        aspect = cell_aspect

    sample_height = max(1, int(round(dot_size * aspect)))
    return sample_height, glyph_cell_width, glyph_cell_height, glyphs


def _compute_ascii_halftone_data(
    image: Image.Image,
    dot_size: int,
    charset: str,
    cell_aspect: Optional[float],
) -> tuple[list[str], int, int, int, Dict[str, Image.Image]]:
    grayscale = ImageOps.grayscale(image)
    width, height = grayscale.size
    dot_size = max(2, dot_size)
    steps = max(len(charset) - 1, 0)
    sample_height, glyph_cell_width, glyph_cell_height, glyphs = _ascii_geometry(
        dot_size, charset, cell_aspect
    )

    lines: list[str] = []
    for top in range(0, height, sample_height):
        row_chars: list[str] = []
        for left in range(0, width, dot_size):
            box = (
                left,
                top,
                min(left + dot_size, width),
                min(top + sample_height, height),
            )
            tile = grayscale.crop(box)
            brightness = _tile_brightness(tile)
            if steps == 0:
                index = 0
            else:
                scale = 1.0 - brightness / 255.0
                index = min(steps, max(0, int(scale * steps + 0.5)))
            row_chars.append(charset[index])
        lines.append("".join(row_chars))
    return lines, sample_height, glyph_cell_width, glyph_cell_height, glyphs


def ascii_halftone_lines(
    image: Image.Image,
    dot_size: int,
    charset: str = DEFAULT_ASCII_CHARSET,
    cell_aspect: Optional[float] = None,
) -> list[str]:
    """Return ASCII art lines representing the supplied *image*."""
    if not charset:
        raise ValueError("charset must contain at least one character")
    if cell_aspect is not None and cell_aspect <= 0:
        raise ValueError("cell_aspect must be positive")
    lines, *_ = _compute_ascii_halftone_data(image, dot_size, charset, cell_aspect)
    return lines


def ascii_lines_to_image(
    lines: list[str],
    glyphs: Dict[str, Image.Image],
    glyph_cell_width: int,
    glyph_cell_height: int,
    target_cell_width: int,
    target_cell_height: int,
) -> Image.Image:
    """Render ASCII lines into a Pillow image for GUI previews."""
    if not lines:
        return Image.new("RGB", (1, 1), color="white")

    max_columns = max(len(line) for line in lines)
    if max_columns == 0 or glyph_cell_width == 0 or glyph_cell_height == 0:
        return Image.new("RGB", (1, 1), color="white")

    image_width = max_columns * glyph_cell_width
    image_height = len(lines) * glyph_cell_height
    image = Image.new("L", (image_width, image_height), color=255)

    for row, line in enumerate(lines):
        y = row * glyph_cell_height
        x = 0
        for char in line:
            glyph = glyphs.get(char)
            if glyph is not None:
                image.paste(glyph, (x, y))
            x += glyph_cell_width

    if glyph_cell_width != target_cell_width or glyph_cell_height != target_cell_height:
        target_width = max_columns * target_cell_width
        target_height = len(lines) * target_cell_height
        image = image.resize((target_width, target_height), Image.NEAREST)

    return image.convert("RGB")


def apply_ascii_halftone(image: Image.Image, dot_size: int) -> Image.Image:
    """Render the image as ASCII art and draw it onto a Pillow image."""
    lines, sample_height, glyph_cell_width, glyph_cell_height, glyphs = _compute_ascii_halftone_data(
        image, dot_size, DEFAULT_ASCII_CHARSET, None
    )
    ascii_image = ascii_lines_to_image(
        lines, glyphs, glyph_cell_width, glyph_cell_height, dot_size, sample_height
    )
    if ascii_image.size != image.size:
        ascii_image = ascii_image.resize(image.size, Image.NEAREST)
    return ascii_image


def ascii_halftone_text(
    image: Image.Image,
    dot_size: int,
    charset: str = DEFAULT_ASCII_CHARSET,
    cell_aspect: Optional[float] = None,
) -> str:
    """Return the ASCII halftone representation as a single string."""
    return "\n".join(ascii_halftone_lines(image, dot_size, charset, cell_aspect))


def merge_with_original(original: Image.Image, overlay: Image.Image) -> Image.Image:
    """Overlay a black-on-white halftone result on top of the original image."""
    base = original.convert("RGBA")
    overlay_gray = overlay.convert("L")
    alpha = ImageOps.invert(overlay_gray)

    if overlay.size != base.size:
        overlay_gray = overlay_gray.resize(base.size, Image.LANCZOS)
        alpha = alpha.resize(base.size, Image.LANCZOS)

    # Blur alpha slightly to soften rough edges from dilation
    alpha = alpha.filter(ImageFilter.GaussianBlur(radius=0.5))
    alpha = ImageOps.autocontrast(alpha)

    foreground = Image.new("RGBA", base.size, color=(0, 0, 0, 0))
    foreground.putalpha(alpha)
    merged = Image.alpha_composite(base, foreground)
    return merged.convert("RGB")


HALFTONE_METHODS: Dict[str, HalftoneMethod] = {
    method.name: method
    for method in (
        HalftoneMethod("Original", apply_identity, "No processing; shows the original image."),
        HalftoneMethod("Grayscale", apply_grayscale, "Convert the image to grayscale."),
        HalftoneMethod(
            "Floyd-Steinberg",
            apply_floyd_steinberg,
            "High quality error-diffusion dithering using Pillow's implementation.",
        ),
        HalftoneMethod(
            "Ordered Dither",
            apply_ordered_dither,
            "Bayer ordered dithering for a structured halftone look.",
        ),
        HalftoneMethod(
            "Circular Halftone",
            apply_circular_halftone,
            "Generates circular dots sized by brightness for a traditional halftone pattern.",
        ),
        HalftoneMethod(
            "ASCII Halftone",
            apply_ascii_halftone,
            "Draws a square halftone using ASCII characters for a terminal-art style look.",
        ),
    )
}


def available_methods() -> Iterable[str]:
    """Return the display names of available halftone methods."""
    return HALFTONE_METHODS.keys()


def describe_method(name: str) -> str:
    """Return a user-friendly description of the halftone method."""
    return HALFTONE_METHODS[name].description


def process_image(image: Image.Image, method_name: str, dot_size: int) -> Image.Image:
    """Apply the selected halftone method to *image*."""
    method = HALFTONE_METHODS.get(method_name)
    if method is None:
        raise ValueError(f"Unknown halftone method: {method_name}")
    return method.apply(image, dot_size)


def scaled_pixmap(image: Image.Image, max_width: int, max_height: int) -> QPixmap:
    """Convert a Pillow image to a ``QPixmap`` sized for preview areas."""
    pixmap = pil_to_qpixmap(image)
    return pixmap.scaled(
        max_width,
        max_height,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
