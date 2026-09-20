"""Tests for converting album artwork bytes into colored ASCII."""

from io import BytesIO

from PIL import Image
from rich.style import Style
from rich.text import Text

from smorg.integrations.spotify.albumart import CELL_ASPECT, image_to_ascii


def png_bytes(color: tuple[int, int, int] = (255, 0, 0), size: int = 8) -> bytes:
    image = Image.new("RGB", (size, size), color)
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def test_a_square_image_is_half_as_tall_as_it_is_wide():
    width = 20
    rendered = image_to_ascii(png_bytes(), width)

    assert rendered is not None
    lines = rendered.plain.splitlines()
    assert len(lines) == int(width * CELL_ASPECT)
    assert all(len(line) == width for line in lines)


def test_pixels_carry_their_color():
    rendered = image_to_ascii(png_bytes((0, 128, 255)), width=4)

    assert rendered is not None
    assert isinstance(rendered, Text)
    spans = rendered._spans
    assert spans
    first_style = spans[0].style
    assert isinstance(first_style, Style)
    color = first_style.color
    assert color is not None
    triplet = color.triplet
    assert triplet is not None
    assert triplet.blue > triplet.red


def test_unreadable_bytes_yield_nothing():
    assert image_to_ascii(b"not an image", width=12) is None
    assert image_to_ascii(b"", width=12) is None
    assert image_to_ascii(png_bytes(), width=0) is None
