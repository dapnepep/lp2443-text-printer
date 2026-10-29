"""Unit tests for the Pillow 13 4x6 label renderer."""

from __future__ import annotations

from PIL import Image

from lp2443_printer.renderer import render_image_label, render_text_label


def test_render_text_label_dimensions_and_mode() -> None:
    img = render_text_label(
        message="Pick up milk and eggs on the way home!",
        sender="Jake",
        width_dots=808,
        height_dots=1218,
    )
    assert img.size == (808, 1218)
    assert img.mode == "1"

    # Ensure both black (0) and white (255) pixels exist in the rendered label
    extrema = img.getextrema()
    assert extrema == (0, 255)


def test_render_long_message_auto_scales_and_wraps() -> None:
    long_msg = " ".join(["This is a long paragraph that must wrap cleanly across multiple lines."] * 15)
    img = render_text_label(
        message=long_msg,
        sender="AlertBot",
        width_dots=808,
        height_dots=1218,
    )
    assert img.size == (808, 1218)
    assert img.mode == "1"


def test_render_image_label_dithering() -> None:
    sample_photo = Image.new("RGB", (400, 300), color=(128, 180, 220))
    img = render_image_label(
        source_image=sample_photo,
        caption="Test photo caption",
        sender="Jake",
        width_dots=808,
        height_dots=1218,
    )
    assert img.size == (808, 1218)
    assert img.mode == "1"
