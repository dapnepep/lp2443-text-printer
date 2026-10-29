"""Unit tests for EPL2 GW bitmap encoding and native text command generation."""

from __future__ import annotations

from PIL import Image

from lp2443_printer.epl2 import (
    build_epl2_bitmap_job,
    build_epl2_native_text_job,
    encode_image_to_gw_bytes,
)


def test_encode_image_to_gw_bytes_white_and_black_polarity() -> None:
    """In EPL2 GW, bit 0 = Black (burn) and bit 1 = White (off)."""
    # 8x1 pure white image -> 1 byte of 0xFF
    white_img = Image.new("L", (8, 1), color=255)
    w_bytes, h_dots, data = encode_image_to_gw_bytes(white_img)
    assert w_bytes == 1
    assert h_dots == 1
    assert data == b"\xff"

    # 8x1 pure black image -> 1 byte of 0x00
    black_img = Image.new("L", (8, 1), color=0)
    w_bytes_b, h_dots_b, data_b = encode_image_to_gw_bytes(black_img)
    assert w_bytes_b == 1
    assert h_dots_b == 1
    assert data_b == b"\x00"


def test_encode_image_pads_non_multiple_of_8_with_white() -> None:
    """Widths not divisible by 8 must be padded with white (1s), not black (0s)."""
    # 5 pixels wide pure white -> should pad remaining 3 bits with 1s -> 0xFF
    img = Image.new("L", (5, 2), color=255)
    w_bytes, h_dots, data = encode_image_to_gw_bytes(img)
    assert w_bytes == 1
    assert h_dots == 2
    assert data == b"\xff\xff"


def test_build_epl2_bitmap_job_structure() -> None:
    img = Image.new("1", (808, 100), color=1)
    payload = build_epl2_bitmap_job(
        image=img,
        label_width_dots=812,
        label_height_dots=1218,
        gap_dots=24,
        speed=2,
        density=10,
    )
    assert b"\nN\nq812\nQ1218,24\nS2\nD10\nZT\nGW2,0,101,100," in payload
    assert payload.endswith(b"\nP1\n")


def test_build_epl2_native_text_job() -> None:
    payload = build_epl2_native_text_job(["Hello LP2443", 'Quote "test"'])
    text = payload.decode("latin-1")
    assert "q812" in text
    assert 'A40,40,0,4,2,2,N,"Hello LP2443"' in text
    assert 'Quote \\"test\\"' in text
    assert "P1" in text
