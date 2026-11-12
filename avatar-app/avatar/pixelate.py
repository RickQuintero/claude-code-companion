"""Tools for turning a render or drawing into small pixel art: cut-out, pixelate, outline, preview sheet.

Used by the pack generators (and by tools/previews.py to compare grid sizes before a character is built).
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw


def cut_out_background(im: Image.Image, tolerance: int = 10) -> Image.Image:
    """Make the outside background transparent: flood fill from the corners over colours close to the corner colour.

    Background that is enclosed by the figure (white inside a ring, say) is kept. An image that already has
    transparency is returned unchanged.
    """
    im = im.convert("RGBA")
    if im.getchannel("A").getextrema()[0] < 255:
        return im
    w, h = im.size
    bg = im.getpixel((0, 0))
    for seed in [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)]:
        px = im.getpixel(seed)
        if px[3] != 0 and sum(abs(a - b) for a, b in zip(px, bg)) <= tolerance:
            ImageDraw.floodfill(im, seed, (0, 0, 0, 0), thresh=tolerance)
    return im


def add_outline(im: Image.Image, colour=(18, 18, 26, 255)) -> Image.Image:
    """Wrap the silhouette with a one-cell outline (up, down, left, right neighbours only)."""
    w, h = im.size
    out = Image.new("RGBA", (w + 2, h + 2), (0, 0, 0, 0))
    out.paste(im, (1, 1))
    src = out.copy()
    for y in range(h + 2):
        for x in range(w + 2):
            if src.getpixel((x, y))[3] == 0 and any(
                    0 <= x + dx < w + 2 and 0 <= y + dy < h + 2 and src.getpixel((x + dx, y + dy))[3] == 255
                    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))):
                out.putpixel((x, y), tuple(colour))
    return out


def pixelate(im: Image.Image, grid_w: int, colors: int = 16, outline=(18, 18, 26, 255)) -> Image.Image:
    """Crop to the figure, shrink it to grid_w cells wide (same shape), limit the palette, optionally outline it."""
    im = im.convert("RGBA")
    solid = im.getchannel("A").point(lambda v: 255 if v > 8 else 0)
    crop = im.crop(solid.getbbox())
    grid_h = max(1, round(crop.height * grid_w / crop.width))
    small = crop.resize((grid_w, grid_h), Image.BOX)            # Pillow averages with premultiplied alpha
    cells = [(x, y) for y in range(grid_h) for x in range(grid_w)]
    opaque = [c for c in cells if small.getpixel(c)[3] >= 128]
    if not opaque:
        return Image.new("RGBA", (grid_w, grid_h), (0, 0, 0, 0))
    mean = tuple(sum(small.getpixel(c)[i] for c in opaque) // len(opaque) for i in range(3))
    rgb = Image.new("RGB", (grid_w, grid_h), mean)
    for c in opaque:
        rgb.putpixel(c, small.getpixel(c)[:3])
    rgb = rgb.quantize(colors=colors, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE).convert("RGB")
    out = Image.new("RGBA", (grid_w, grid_h), (0, 0, 0, 0))
    for c in opaque:
        out.putpixel(c, (*rgb.getpixel(c), 255))
    return add_outline(out, outline) if outline else out


def preview_sheet(variants: list[tuple[str, Image.Image]], out: Path, tile_h: int = 260) -> None:
    """Side-by-side tiles of each (label, image), once on a dark and once on a light background."""
    pad, label_h = 10, 16
    tiles = []
    for label, im in variants:
        scale = max(1, tile_h // im.height)
        tiles.append((label, im.resize((im.width * scale, im.height * scale), Image.NEAREST) if scale > 1 else im))
    width = sum(t.width + pad for _, t in tiles) + pad
    row_h = tile_h + label_h + pad
    sheet = Image.new("RGBA", (width, row_h * 2), (30, 30, 34, 255))
    ImageDraw.Draw(sheet).rectangle([0, row_h, width, row_h * 2], fill=(236, 236, 240, 255))
    d = ImageDraw.Draw(sheet)
    x = pad
    for label, tile in tiles:
        for row, ink in ((0, (220, 220, 220, 255)), (1, (40, 40, 40, 255))):
            d.text((x, row * row_h + 2), f"{label}  ({tile.width}x{tile.height}px)", fill=ink)
            sheet.alpha_composite(tile, (x, row * row_h + label_h + (tile_h - tile.height) // 2))
        x += tile.width + pad
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)
