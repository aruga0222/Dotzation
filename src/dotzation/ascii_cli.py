"""Command line utilities for ASCII halftone output."""

from __future__ import annotations

import argparse
from pathlib import Path

from . import halftone


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Render an image as ASCII halftone art and print it to the terminal."
    )
    parser.add_argument("image", type=Path, help="Path to the source image file.")
    parser.add_argument(
        "--dot-size",
        type=int,
        default=8,
        help="Size of each sampled block in pixels (default: 8).",
    )
    parser.add_argument(
        "--charset",
        default=halftone.DEFAULT_ASCII_CHARSET,
        help=f"Characters to use from light to dark (default: {halftone.DEFAULT_ASCII_CHARSET!r}).",
    )
    parser.add_argument(
        "--char-aspect",
        type=float,
        default=None,
        help=(
            "Height/width ratio for the character grid. "
            f"Defaults to the bundled font's ratio ({halftone.DEFAULT_ASCII_ASPECT:.2f})."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.dot_size < 2:
        parser.error("--dot-size must be >= 2")

    if not args.charset:
        parser.error("--charset must contain at least one character")
    if args.char_aspect is not None and args.char_aspect <= 0:
        parser.error("--char-aspect must be positive")

    image_path = args.image
    if not image_path.exists():
        parser.error(f"Image not found: {image_path}")

    image = halftone.load_image(str(image_path))
    ascii_lines = halftone.ascii_halftone_lines(
        image, args.dot_size, args.charset, args.char_aspect
    )
    print("\n".join(ascii_lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
