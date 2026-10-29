"""Command-line interface (`lp2443`) for probing, test-printing, previewing, and running the server."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import uvicorn

from lp2443_printer.config import settings
from lp2443_printer.service import PrinterService


def main(argv: list[str] | None = None) -> int:
    """Entry point for the `lp2443` CLI."""
    parser = argparse.ArgumentParser(
        prog="lp2443",
        description="Eltron/Zebra LP2443PSA Text-to-Label Printer CLI (QinHeng CH340S USB-LPT)",
    )
    parser.add_argument(
        "--device",
        default=None,
        help="Override printer device node (default: auto-detect 1a86:7584 or /dev/lp2443)",
    )
    parser.add_argument(
        "--invert",
        action="store_true",
        help="Invert bitmap bits (use if firmware prints negative/inverted labels)",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # 1. probe
    subparsers.add_parser("probe", help="Detect connected QinHeng USB-LPT converter and check permissions")

    # 2. test-print
    tp_parser = subparsers.add_parser("test-print", help="Print a 4x6 diagnostic test label on the LP2443PSA")
    tp_parser.add_argument(
        "--native",
        action="store_true",
        help="Use lightweight native EPL2 ASCII font instead of full GW bitmap rendering",
    )

    # 3. print
    p_parser = subparsers.add_parser("print", help="Render and print a text message onto a 4x6 label")
    p_parser.add_argument("message", help="Text message to print")
    p_parser.add_argument("--sender", default="", help="Optional sender name in header banner")
    p_parser.add_argument("--no-header", action="store_true", help="Omit top sender/timestamp bar")
    p_parser.add_argument("--no-border", action="store_true", help="Omit outer rounded border")
    p_parser.add_argument("--copies", type=int, default=1, help="Number of label copies")
    p_parser.add_argument("--save-preview", default=None, help="Also save rendered PNG to this path")

    # 4. preview
    prev_parser = subparsers.add_parser("preview", help="Render a message to a PNG file without printing")
    prev_parser.add_argument("message", help="Text message to render")
    prev_parser.add_argument("-o", "--output", default="preview_label.png", help="Output PNG path")
    prev_parser.add_argument("--sender", default="Jake", help="Sender name for header")

    # 5. serve
    srv_parser = subparsers.add_parser(
        "serve",
        help="Start the FastAPI Web UI / Webhook server and Telegram Bot listener",
    )
    srv_parser.add_argument("--host", default=None, help="Bind host (default: 0.0.0.0)")
    srv_parser.add_argument("--port", type=int, default=None, help="Bind port (default: 8000)")

    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    cfg = settings.model_copy(deep=True)
    if args.device:
        cfg.device_path = args.device
    if args.invert:
        cfg.invert_bitmap = True

    service = PrinterService(cfg)

    if args.command == "probe":
        info = service.probe()
        if info is None:
            print("❌ Printer NOT found. Make sure the QinHeng USB-LPT cable (1a86:7584) is plugged in.")
            return 1
        print("✅ Printer Detected!")
        print(f"   Device Node : {info.device_node}")
        print(f"   Hardware ID : {info.vendor_id}:{info.product_id} ({info.product_name})")
        writable_msg = (
            "YES ✅"
            if info.writable
            else f"NO ❌ (run: sudo usermod -aG lp $USER && sudo chmod 666 {info.device_node})"
        )
        print(f"   Writable    : {writable_msg}")
        return 0 if info.writable else 2

    if args.command == "preview":
        img = service.render_message(message=args.message, sender=args.sender)
        out_path = Path(args.output)
        img.save(out_path)
        print(f"✅ Saved 4x6 label preview ({img.width}x{img.height} dots) to {out_path.resolve()}")
        return 0

    if args.command == "test-print":
        try:
            if args.native:
                written = service.print_native_test()
            else:
                test_msg = (
                    "Hello from Raspberry Pi!\n\n"
                    "LP2443PSA + QinHeng CH340S (1a86:7584) is ready to print your texts!"
                )
                written = service.print_text(
                    message=test_msg,
                    sender="SYSTEM TEST",
                )
            print(f"✅ Test label sent successfully ({written:,} bytes written).")
            return 0
        except Exception as exc:
            print(f"❌ Test print failed: {exc}", file=sys.stderr)
            return 1

    if args.command == "print":
        try:
            written = service.print_text(
                message=args.message,
                sender=args.sender,
                show_header=not args.no_header,
                show_border=not args.no_border,
                copies=args.copies,
                save_preview_path=args.save_preview,
            )
            print(f"✅ Printed message ({written:,} bytes written).")
            return 0
        except Exception as exc:
            print(f"❌ Print failed: {exc}", file=sys.stderr)
            return 1

    if args.command == "serve":
        host = args.host or cfg.host
        port = args.port or cfg.port
        uvicorn.run(
            "lp2443_printer.server:app",
            host=host,
            port=port,
            reload=False,
        )
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
