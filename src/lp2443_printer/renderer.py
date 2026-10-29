"""Pillow-based 4x6 label renderer with dynamic font auto-scaling and word-wrapping."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

FONT_SEARCH_PATHS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
    "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
]

MONO_FONT_SEARCH_PATHS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    "/usr/share/fonts/truetype/noto/NotoSansMono-Regular.ttf",
]


def load_font(size: int, mono: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Load a TrueType font from standard Debian paths, with graceful fallback."""
    candidates = MONO_FONT_SEARCH_PATHS if mono else FONT_SEARCH_PATHS
    for path_str in candidates:
        if Path(path_str).exists():
            try:
                return ImageFont.truetype(path_str, size=size)
            except OSError:
                continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def wrap_text_to_width(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    max_width_px: int,
) -> list[str]:
    """Word-wrap text (preserving explicit newlines and breaking oversized words) to fit max_width_px."""
    lines: list[str] = []
    paragraphs = text.replace("\r\n", "\n").split("\n")

    for paragraph in paragraphs:
        if not paragraph.strip():
            lines.append("")
            continue

        words = paragraph.split(" ")
        current_line = ""

        for word in words:
            candidate = word if not current_line else f"{current_line} {word}"
            bbox = draw.textbbox((0, 0), candidate, font=font)
            width = bbox[2] - bbox[0]

            if width <= max_width_px:
                current_line = candidate
            else:
                if current_line:
                    lines.append(current_line)
                    current_line = ""

                # Check if single word itself exceeds max_width_px
                word_bbox = draw.textbbox((0, 0), word, font=font)
                if (word_bbox[2] - word_bbox[0]) <= max_width_px:
                    current_line = word
                else:
                    # Character-by-character split for very long unbroken strings/URLs
                    chunk = ""
                    for ch in word:
                        test_chunk = chunk + ch
                        cb = draw.textbbox((0, 0), test_chunk, font=font)
                        if (cb[2] - cb[0]) <= max_width_px:
                            chunk = test_chunk
                        else:
                            if chunk:
                                lines.append(chunk)
                            chunk = ch
                    current_line = chunk

        if current_line:
            lines.append(current_line)

    return lines if lines else [""]


def render_text_label(
    message: str,
    sender: str = "",
    timestamp: datetime | None = None,
    width_dots: int = 808,
    height_dots: int = 1218,
    margin_px: int = 32,
    show_header: bool = True,
    show_border: bool = True,
    max_font_size: int = 110,
    min_font_size: int = 24,
) -> Image.Image:
    """Render a text message onto a 1-bit monochrome label canvas with auto-scaling font size.

    Note: `width_dots=808` (101 bytes * 8) fits cleanly inside an 812-dot 4" printhead
    with a 2-dot margin on each side and avoids any byte-padding misalignment.
    """
    # Ensure width is a multiple of 8 for clean EPL2 GW byte packing
    canvas_width = (width_dots // 8) * 8
    canvas_height = height_dots

    # Create grayscale canvas first for crisp layout, convert to 1-bit at the end
    img = Image.new("L", (canvas_width, canvas_height), color=255)
    draw = ImageDraw.Draw(img)

    # Outer border
    if show_border:
        draw.rounded_rectangle(
            (8, 8, canvas_width - 9, canvas_height - 9),
            radius=20,
            outline=0,
            width=6,
        )

    content_top = margin_px
    content_bottom = canvas_height - margin_px
    content_left = margin_px
    content_right = canvas_width - margin_px
    usable_width = content_right - content_left

    # Optional Header Banner (Sender + Timestamp)
    if show_header:
        ts_str = (timestamp or datetime.now()).strftime("%Y-%m-%d  %I:%M %p")
        header_font = load_font(28, mono=True)
        sender_label = f"FROM: {sender}" if sender else "INCOMING MESSAGE"

        # Draw inverted black header bar at top inside border
        header_box_top = 20
        header_box_bottom = 112
        draw.rounded_rectangle(
            (20, header_box_top, canvas_width - 21, header_box_bottom),
            radius=12,
            fill=0,
        )
        draw.text((38, header_box_top + 12), sender_label[:38], font=header_font, fill=255)
        draw.text((38, header_box_top + 50), ts_str, font=header_font, fill=255)
        content_top = header_box_bottom + 28

    usable_height = content_bottom - content_top

    # Dynamic Font Auto-Scaling: find largest font that fits both width and height
    chosen_font = load_font(min_font_size)
    chosen_lines: list[str] = []
    chosen_line_height = min_font_size + 8

    for font_size in range(max_font_size, min_font_size - 1, -4):
        font = load_font(font_size)
        wrapped = wrap_text_to_width(draw, message.strip() or "(Empty Message)", font, usable_width)
        line_spacing = max(8, int(font_size * 0.22))
        sample_bbox = draw.textbbox((0, 0), "Ag", font=font)
        single_line_h = (sample_bbox[3] - sample_bbox[1]) + line_spacing
        total_h = single_line_h * len(wrapped)

        if total_h <= usable_height:
            chosen_font = font
            chosen_lines = wrapped
            chosen_line_height = single_line_h
            break
    else:
        chosen_font = load_font(min_font_size)
        chosen_lines = wrap_text_to_width(draw, message.strip() or "(Empty Message)", chosen_font, usable_width)
        sample_bbox = draw.textbbox((0, 0), "Ag", font=chosen_font)
        chosen_line_height = (sample_bbox[3] - sample_bbox[1]) + 6
        max_visible_lines = max(1, usable_height // chosen_line_height)
        if len(chosen_lines) > max_visible_lines:
            chosen_lines = chosen_lines[:max_visible_lines]
            chosen_lines[-1] = chosen_lines[-1][: max(1, len(chosen_lines[-1]) - 3)] + "..."

    # Vertically center the text block when there are few lines
    total_text_height = len(chosen_lines) * chosen_line_height
    y_cursor = content_top + max(0, (usable_height - total_text_height) // 2)

    for line in chosen_lines:
        # Center-align short single/double lines, left-align longer multi-line paragraphs
        if len(chosen_lines) <= 3:
            lb = draw.textbbox((0, 0), line, font=chosen_font)
            lw = lb[2] - lb[0]
            x_cursor = content_left + max(0, (usable_width - lw) // 2)
        else:
            x_cursor = content_left

        draw.text((x_cursor, y_cursor), line, font=chosen_font, fill=0)
        y_cursor += chosen_line_height

    # Convert to strict 1-bit monochrome (0=black, 255=white)
    return img.point(lambda p: 255 if p > 128 else 0, mode="1")


def render_image_label(
    source_image: Image.Image,
    caption: str = "",
    sender: str = "",
    width_dots: int = 808,
    height_dots: int = 1218,
) -> Image.Image:
    """Render an attached photo/image (with Floyd-Steinberg dithering) and optional caption onto a 4x6 label."""
    canvas_width = (width_dots // 8) * 8
    canvas_height = height_dots
    canvas = Image.new("L", (canvas_width, canvas_height), color=255)
    draw = ImageDraw.Draw(canvas)

    top_offset = 24
    if sender:
        hdr_font = load_font(26, mono=True)
        draw.text((24, top_offset), f"FROM: {sender}", font=hdr_font, fill=0)
        top_offset += 44

    caption_height = 160 if caption else 24
    avail_h = canvas_height - top_offset - caption_height - 24
    avail_w = canvas_width - 48

    # Resize image preserving aspect ratio and apply autocontrast + dithering
    gray = ImageOps.exif_transpose(source_image).convert("L")
    gray = ImageOps.autocontrast(gray)
    gray.thumbnail((avail_w, avail_h), Image.Resampling.LANCZOS)

    # Dither the photo portion to 1-bit for thermal printing
    dithered_photo = gray.convert("1", dither=Image.Dither.FLOYDSTEINBERG)
    paste_x = (canvas_width - dithered_photo.width) // 2
    paste_y = top_offset + (avail_h - dithered_photo.height) // 2

    bw_canvas = canvas.point(lambda p: 255 if p > 128 else 0, mode="1")
    bw_canvas.paste(dithered_photo, (paste_x, paste_y))

    if caption:
        cap_draw = ImageDraw.Draw(bw_canvas)
        cap_font = load_font(36)
        lines = wrap_text_to_width(cap_draw, caption, cap_font, avail_w)[:3]
        cy = top_offset + avail_h + 16
        for ln in lines:
            cap_draw.text((24, cy), ln, font=cap_font, fill=0)
            cy += 44

    return bw_canvas
