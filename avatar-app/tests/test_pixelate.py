from PIL import Image, ImageDraw

from avatar.pixelate import add_outline, cut_out_background, pixelate, preview_sheet

WHITE, RED, BLUE = (255, 255, 255, 255), (220, 30, 30, 255), (30, 30, 220, 255)


def ring_on_white(size=40):
    """White background, a red ring, and white inside the ring (the inside must survive the cut-out)."""
    im = Image.new("RGBA", (size, size), WHITE)
    d = ImageDraw.Draw(im)
    d.ellipse([8, 8, 31, 31], fill=RED)
    d.ellipse([14, 14, 25, 25], fill=WHITE)
    return im


def test_cut_out_removes_the_outside_background_only():
    out = cut_out_background(ring_on_white())
    assert out.getpixel((1, 1))[3] == 0 and out.getpixel((38, 38))[3] == 0     # outside is gone
    assert out.getpixel((10, 20)) == RED                                       # the ring stays
    assert out.getpixel((20, 20)) == WHITE                                     # enclosed white stays opaque


def test_cut_out_tolerates_a_slightly_noisy_background():
    im = ring_on_white()
    im.putpixel((2, 2), (250, 252, 255, 255))
    assert cut_out_background(im, tolerance=12).getpixel((2, 2))[3] == 0


def test_cut_out_leaves_an_already_transparent_image_alone():
    im = Image.new("RGBA", (10, 10), (0, 0, 0, 0))
    im.putpixel((5, 5), RED)
    out = cut_out_background(im)
    assert out.getpixel((5, 5)) == RED and out.getpixel((0, 0))[3] == 0


def test_pixelate_makes_a_grid_of_the_requested_width_with_the_same_shape():
    im = Image.new("RGBA", (100, 200), (0, 0, 0, 0))
    ImageDraw.Draw(im).rectangle([10, 20, 89, 179], fill=BLUE)          # 80 x 160 object
    out = pixelate(im, grid_w=10, colors=4, outline=None)
    assert out.size == (10, 20)                                          # cropped to the object, same 1:2 shape
    assert all(out.getpixel((x, y)) == BLUE for x in range(10) for y in range(20))


def test_pixelate_keeps_transparent_cells_transparent_and_limits_the_palette():
    im = ring_on_white(120)
    out = pixelate(cut_out_background(im), grid_w=24, colors=3, outline=None)
    colours = {out.getpixel((x, y)) for x in range(out.width) for y in range(out.height) if out.getpixel((x, y))[3] == 255}
    assert len(colours) <= 3
    assert out.getpixel((0, 0))[3] == 0                                 # the corner of the circle's box is empty


def test_outline_wraps_the_silhouette_with_one_cell():
    im = Image.new("RGBA", (3, 3), (0, 0, 0, 0))
    im.putpixel((1, 1), RED)
    out = add_outline(im, (10, 10, 10, 255))
    assert out.size == (5, 5) and out.getpixel((2, 2)) == RED
    for xy in [(1, 2), (3, 2), (2, 1), (2, 3)]:
        assert out.getpixel(xy) == (10, 10, 10, 255)
    assert out.getpixel((1, 1))[3] == 0                                  # diagonal neighbours stay empty


def test_preview_sheet_shows_each_variant_on_dark_and_light(tmp_path):
    a = Image.new("RGBA", (8, 10), RED)
    b = Image.new("RGBA", (16, 20), BLUE)
    out = tmp_path / "sheet.png"
    preview_sheet([("8", a), ("16", b)], out, tile_h=60)
    sheet = Image.open(out)
    assert sheet.height >= 120 and sheet.width >= 60
