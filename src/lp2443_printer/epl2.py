"""EPL2 (Eltron Programming Language 2) command generator for the LP2443PSA."""

from __future__ import annotations

from PIL import Image, ImageOps


def encode_image_to_gw_bytes(
    image: Image.Image,
    invert: bool = False,
) -> tuple[int, int, bytes]:
    """Convert a Pillow Image into EPL2 GW raw monochrome bytes.

    In standard EPL2 `GW x,y,width_bytes,height_dots,DATA`:
      - Bit 0 = Black dot (thermal element ON)
      - Bit 1 = White dot (thermal element OFF)

    In Pillow `mode="1"`:
      - Pixel 0 = Black, Pixel 255 (bit 1) = White.
      - However, if an image width is not a multiple of 8, Pillow pads the trailing bits
        on the right of each row with 0s (which EPL2 would print as solid black bars!).
      - Therefore, we always pad the image width with white pixels (255) to an exact
        multiple of 8 before calling `.tobytes()`.

    Returns:
        (width_bytes, height_dots, raw_data_bytes)
    """
    # Convert to grayscale then 1-bit monochrome if needed
    if image.mode != "1":
        bw = image.convert("L").point(lambda p: 255 if p > 128 else 0, mode="1")
    else:
        bw = image.copy()

    width_px, height_px = bw.size
    padded_width_px = ((width_px + 7) // 8) * 8
    if padded_width_px != width_px:
        padded = Image.new("1", (padded_width_px, height_px), color=1)  # 1 = White
        padded.paste(bw, (0, 0))
        bw = padded

    if invert:
        # Invert in "L" space so 0 <-> 255 cleanly
        bw = ImageOps.invert(bw.convert("L")).convert("1")

    width_bytes = padded_width_px // 8
    raw_bytes = bw.tobytes()
    assert len(raw_bytes) == width_bytes * height_px
    return width_bytes, height_px, raw_bytes


def build_epl2_bitmap_job(
    image: Image.Image,
    label_width_dots: int = 812,
    label_height_dots: int = 1218,
    gap_dots: int = 24,
    speed: int = 2,
    density: int = 10,
    x_offset: int = 2,
    y_offset: int = 0,
    copies: int = 1,
    invert_bitmap: bool = False,
) -> bytes:
    """Build a complete EPL2 command stream using the GW (Direct Graphic Write) command."""
    width_bytes, height_dots, raw_data = encode_image_to_gw_bytes(image, invert=invert_bitmap)

    header_lines = [
        "",  # Leading newline to clear any stale partial line in printer buffer
        "N",  # Clear image buffer
        f"q{label_width_dots}",  # Set label width in dots
        f"Q{label_height_dots},{gap_dots}",  # Set label height and gap length in dots
        f"S{speed}",  # Set print speed
        f"D{density}",  # Set print density/darkness
        "ZT",  # Print from top of image buffer
    ]
    header_bytes = ("\n".join(header_lines) + "\n").encode("ascii")
    gw_prefix = f"GW{x_offset},{y_offset},{width_bytes},{height_dots},".encode("ascii")
    footer_bytes = f"\nP{max(1, copies)}\n".encode("ascii")

    return header_bytes + gw_prefix + raw_data + footer_bytes


def build_epl2_native_text_job(
    lines: list[str],
    label_width_dots: int = 812,
    label_height_dots: int = 1218,
    gap_dots: int = 24,
    speed: int = 2,
    density: int = 10,
    font: int = 4,
    h_mult: int = 2,
    v_mult: int = 2,
) -> bytes:
    """Build a lightweight native EPL2 ASCII text job using the `A` command (useful for quick probes)."""
    cmds = [
        "",
        "N",
        f"q{label_width_dots}",
        f"Q{label_height_dots},{gap_dots}",
        f"S{speed}",
        f"D{density}",
        "ZT",
    ]
    y_pos = 40
    line_step = 36 * v_mult
    for line in lines:
        safe_text = line.replace("\\", "\\\\").replace('"', '\\"')
        cmds.append(f'A40,{y_pos},0,{font},{h_mult},{v_mult},N,"{safe_text}"')
        y_pos += line_step
        if y_pos >= label_height_dots - 40:
            break

    cmds.append("P1")
    cmds.append("")
    return "\n".join(cmds).encode("latin-1", errors="replace")
