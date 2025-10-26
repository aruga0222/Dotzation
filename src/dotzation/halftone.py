"""Halftone and dithering utilities for Dotzation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, Iterable

from PIL import Image, ImageDraw, ImageOps
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
