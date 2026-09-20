"""Turn album artwork bytes into colored terminal ASCII."""

from __future__ import annotations

from io import BytesIO

from rich.color import Color
from rich.style import Style
from rich.text import Text

# Characters go from dark -> bright.
CHARS = ' .`^",:;Il!i~+_-?][}{1)(|\\/~tfjrxnuvczXYUJCLQ0OZmwqpdbkhao*#MW&8%B@$'
# Terminal cells are roughly twice as tall as they are wide.
CELL_ASPECT = 0.5


def image_to_ascii(data: bytes, width: int) -> Text | None:
    """Colored ASCII art of `data`, `width` cells wide, or None if the bytes are not an image.

    Pillow is imported lazily so a missing or broken install just turns the cover off rather than
    crashing the tab (and lets the dependency be optional).
    """
    if width < 1 or not data:
        return None
    try:
        from PIL import Image
    except ImportError:
        return None
    try:
        image = Image.open(BytesIO(data)).convert("RGB")
    except (OSError, ValueError):
        return None
    original_width, original_height = image.size
    if original_width < 1 or original_height < 1:
        return None
    height = max(1, int((original_height / original_width) * width * CELL_ASPECT))
    image = image.resize((width, height), Image.Resampling.LANCZOS)
    pixels = image.load()
    if pixels is None:
        return None
    max_char_index = len(CHARS) - 1
    lines: list[Text] = []
    for y in range(height):
        line = Text()
        for x in range(width):
            pixel = pixels[x, y]
            if not isinstance(pixel, tuple):
                continue
            red = int(pixel[0])
            green = int(pixel[1])
            blue = int(pixel[2])
            luminance = 0.2126 * red + 0.7152 * green + 0.0722 * blue
            char_index = int((luminance / 255) * max_char_index)
            char = CHARS[char_index]
            color = Color.from_rgb(red, green, blue)
            line.append(char, style=Style(color=color))
        lines.append(line)
    body = Text("\n").join(lines)
    body.no_wrap = True
    return body
