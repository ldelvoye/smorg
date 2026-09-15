#!/usr/bin/env python3

import argparse
import sys
from PIL import Image, ImageEnhance

# Characters go from dark -> bright.
DEFAULT_CHARS = " .`^\",:;Il!i~+_-?][}{1)(|\\/~tfjrxnuvczXYUJCLQ0OZmwqpdbkhao*#MW&8%B@$"


def image_to_ascii(image_path, width=100, contrast=1.0, brightness=1.0):
    try:
        img = Image.open(image_path).convert("RGB")
    except Exception as e:
        print(f"Error opening image: {e}", file=sys.stderr)
        sys.exit(1)

    # Improve contrast/brightness if requested.
    if contrast != 1.0:
        img = ImageEnhance.Contrast(img).enhance(contrast)

    if brightness != 1.0:
        img = ImageEnhance.Brightness(img).enhance(brightness)

    original_width, original_height = img.size

    # Terminal characters are roughly twice as tall as they are wide.
    # Compensate for that so the image doesn't look stretched vertically.
    height = max(1, int((original_height / original_width) * width * 0.5))

    img = img.resize((width, height), Image.Resampling.LANCZOS)

    chars = DEFAULT_CHARS
    max_char_index = len(chars) - 1

    output = []

    for y in range(height):
        line = []

        for x in range(width):
            r, g, b = img.getpixel((x, y))

            # Perceived brightness (better than a simple RGB average).
            luminance = (
                0.2126 * r +
                0.7152 * g +
                0.0722 * b
            )

            char_index = int((luminance / 255) * max_char_index)
            char = chars[char_index]

            # True-color ANSI escape sequence.
            line.append(
                f"\033[38;2;{r};{g};{b}m{char}"
            )

        line.append("\033[0m")
        output.append("".join(line))

    return "\n".join(output)


def main():
    parser = argparse.ArgumentParser(
        description="Convert album artwork into colored terminal ASCII art."
    )

    parser.add_argument(
        "image",
        help="Path to album artwork (jpg, png, webp, etc.)"
    )

    parser.add_argument(
        "-w",
        "--width",
        type=int,
        default=100,
        help="Output width in characters (default: 100)"
    )

    parser.add_argument(
        "-c",
        "--contrast",
        type=float,
        default=1.0,
        help="Contrast multiplier (default: 1.0)"
    )

    parser.add_argument(
        "-b",
        "--brightness",
        type=float,
        default=1.0,
        help="Brightness multiplier (default: 1.0)"
    )

    parser.add_argument(
        "--no-color",
        action="store_true",
        help="Disable ANSI colors"
    )

    args = parser.parse_args()

    if args.width < 10:
        parser.error("Width must be at least 10.")

    try:
        img = Image.open(args.image).convert("RGB")
    except Exception as e:
        print(f"Error opening image: {e}", file=sys.stderr)
        sys.exit(1)

    # Adjust image.
    if args.contrast != 1.0:
        img = ImageEnhance.Contrast(img).enhance(args.contrast)

    if args.brightness != 1.0:
        img = ImageEnhance.Brightness(img).enhance(args.brightness)

    original_width, original_height = img.size

    height = max(
        1,
        int((original_height / original_width) * args.width * 0.5)
    )

    img = img.resize(
        (args.width, height),
        Image.Resampling.LANCZOS
    )

    chars = DEFAULT_CHARS
    max_char_index = len(chars) - 1

    for y in range(height):
        line = []

        for x in range(args.width):
            r, g, b = img.getpixel((x, y))

            # Perceived brightness.
            luminance = (
                0.2126 * r +
                0.7152 * g +
                0.0722 * b
            )

            char_index = int(
                (luminance / 255) * max_char_index
            )

            char = chars[char_index]

            if args.no_color:
                line.append(char)
            else:
                line.append(
                    f"\033[38;2;{r};{g};{b}m{char}"
                )

        if not args.no_color:
            line.append("\033[0m")

        print("".join(line))


if __name__ == "__main__":
    main()