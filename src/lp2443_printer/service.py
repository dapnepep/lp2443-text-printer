"""High-level print orchestration combining rendering, EPL2 encoding, and USB-LPT transport."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PIL import Image

from lp2443_printer.config import PrinterSettings, settings
from lp2443_printer.epl2 import build_epl2_bitmap_job, build_epl2_native_text_job
from lp2443_printer.hardware import DiscoveredPrinter, PrinterTransport, discover_printer
from lp2443_printer.renderer import render_image_label, render_text_label


class PrinterService:
    """High-level service for rendering and sending print jobs to the LP2443PSA."""

    def __init__(self, cfg: PrinterSettings | None = None) -> None:
        self.cfg = cfg or settings
        self.transport = PrinterTransport(
            device_path=self.cfg.device_path,
            vendor_id=self.cfg.usb_vendor_id,
            product_id=self.cfg.usb_product_id,
        )

    def probe(self) -> DiscoveredPrinter | None:
        """Probe for the connected LP2443PSA / QinHeng CH340S device."""
        return discover_printer(
            preferred_path=self.cfg.device_path,
            target_vendor=self.cfg.usb_vendor_id,
            target_product=self.cfg.usb_product_id,
        )

    def render_message(
        self,
        message: str,
        sender: str = "",
        show_header: bool = True,
        show_border: bool = True,
    ) -> Image.Image:
        """Render a text message to a 1-bit Pillow image."""
        bitmap_width = ((self.cfg.label_width_dots - 4) // 8) * 8
        return render_text_label(
            message=message,
            sender=sender,
            timestamp=datetime.now(),
            width_dots=bitmap_width,
            height_dots=self.cfg.label_height_dots,
            show_header=show_header,
            show_border=show_border,
        )

    def print_text(
        self,
        message: str,
        sender: str = "",
        show_header: bool = True,
        show_border: bool = True,
        copies: int = 1,
        save_preview_path: str | Path | None = None,
    ) -> int:
        """Render a text message into a 4x6 bitmap and send it to the LP2443PSA."""
        img = self.render_message(
            message=message,
            sender=sender,
            show_header=show_header,
            show_border=show_border,
        )
        if save_preview_path:
            img.save(save_preview_path)

        payload = build_epl2_bitmap_job(
            image=img,
            label_width_dots=self.cfg.label_width_dots,
            label_height_dots=self.cfg.label_height_dots,
            gap_dots=self.cfg.gap_dots,
            speed=self.cfg.speed,
            density=self.cfg.density,
            copies=copies,
            invert_bitmap=self.cfg.invert_bitmap,
        )
        return self.transport.send_raw(payload)

    def print_image(
        self,
        source_image: Image.Image,
        caption: str = "",
        sender: str = "",
        copies: int = 1,
    ) -> int:
        """Render a photo/image with dithering and send it to the LP2443PSA."""
        bitmap_width = ((self.cfg.label_width_dots - 4) // 8) * 8
        img = render_image_label(
            source_image=source_image,
            caption=caption,
            sender=sender,
            width_dots=bitmap_width,
            height_dots=self.cfg.label_height_dots,
        )
        payload = build_epl2_bitmap_job(
            image=img,
            label_width_dots=self.cfg.label_width_dots,
            label_height_dots=self.cfg.label_height_dots,
            gap_dots=self.cfg.gap_dots,
            speed=self.cfg.speed,
            density=self.cfg.density,
            copies=copies,
            invert_bitmap=self.cfg.invert_bitmap,
        )
        return self.transport.send_raw(payload)

    def print_native_test(self) -> int:
        """Send a lightweight native EPL2 ASCII + GW test label."""
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        lines = [
            "LP2443PSA READY!",
            "Driver: QinHeng CH340S",
            "USB ID: 1a86:7584",
            f"Size: {self.cfg.label_width_dots}x{self.cfg.label_height_dots} (4x6 in)",
            f"Time: {now_str}",
            "Status: Plug & Play OK",
        ]
        payload = build_epl2_native_text_job(
            lines=lines,
            label_width_dots=self.cfg.label_width_dots,
            label_height_dots=self.cfg.label_height_dots,
            gap_dots=self.cfg.gap_dots,
            speed=self.cfg.speed,
            density=self.cfg.density,
        )
        return self.transport.send_raw(payload)
