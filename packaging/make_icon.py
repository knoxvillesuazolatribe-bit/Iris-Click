"""Draws the IrisClick shortcut icon (an eye in a teal circle) as a Windows .ico.

    python make_icon.py <output.ico>

Uses Pillow (already an IrisClick dependency); no image files are needed.
"""

import sys

from PIL import Image, ImageDraw

TEAL = (15, 118, 110, 255)
WHITE = (255, 255, 255, 255)
DARK = (17, 24, 39, 255)
YELLOW = (250, 204, 21, 255)


def draw(size: int = 256) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    s = size / 256
    d.ellipse((8 * s, 8 * s, 248 * s, 248 * s), fill=TEAL)
    # Eye outline: two arcs meeting at the corners.
    d.chord((36 * s, 70 * s, 220 * s, 186 * s), 0, 360, fill=WHITE)
    d.ellipse((92 * s, 82 * s, 164 * s, 154 * s), fill=DARK)          # iris
    d.ellipse((112 * s, 102 * s, 144 * s, 134 * s), fill=YELLOW)      # pupil highlight
    d.ellipse((136 * s, 94 * s, 150 * s, 108 * s), fill=WHITE)        # glint
    return img


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "irisclick.ico"
    draw().save(out, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print(out)
