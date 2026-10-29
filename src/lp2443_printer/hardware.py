"""Hardware discovery and raw transport for the QinHeng CH340S USB-to-LPT converter."""

from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DiscoveredPrinter:
    """Metadata about a discovered USB printer device."""

    device_node: str
    vendor_id: str
    product_id: str
    product_name: str
    writable: bool


def discover_printer(
    preferred_path: str = "auto",
    target_vendor: str = "1a86",
    target_product: str = "7584",
) -> DiscoveredPrinter | None:
    """Locate the LP2443PSA via sysfs (QinHeng 1a86:7584) or fallback device nodes."""
    # 1. Explicit path if not "auto"
    if preferred_path and preferred_path.lower() != "auto":
        node = Path(preferred_path)
        if node.exists():
            writable = os.access(node, os.W_OK)
            return DiscoveredPrinter(
                device_node=str(node),
                vendor_id=target_vendor,
                product_id=target_product,
                product_name="Configured Device",
                writable=writable,
            )

    # 2. Check custom udev symlink /dev/lp2443 first
    udev_symlink = Path("/dev/lp2443")
    if udev_symlink.exists():
        writable = os.access(udev_symlink, os.W_OK)
        return DiscoveredPrinter(
            device_node="/dev/lp2443",
            vendor_id=target_vendor,
            product_id=target_product,
            product_name="QinHeng CH340S USB2.0-Print (/dev/lp2443)",
            writable=writable,
        )

    # 3. Walk /sys/class/usbmisc/lp* to match idVendor/idProduct
    sys_usbmisc = Path("/sys/class/usbmisc")
    if sys_usbmisc.exists():
        for lp_dir in sorted(sys_usbmisc.glob("lp*")):
            dev_name = lp_dir.name  # e.g. "lp0"
            dev_node = Path("/dev/usb") / dev_name
            if not dev_node.exists():
                dev_node = Path("/dev") / dev_name

            # Walk up sysfs parents to read idVendor and idProduct
            resolved = lp_dir.resolve()
            vendor_id = ""
            product_id = ""
            product_name = "USB Printer"
            for parent in [resolved, *resolved.parents]:
                v_file = parent / "idVendor"
                p_file = parent / "idProduct"
                if v_file.exists() and p_file.exists():
                    vendor_id = v_file.read_text(errors="ignore").strip().lower()
                    product_id = p_file.read_text(errors="ignore").strip().lower()
                    prod_file = parent / "product"
                    if prod_file.exists():
                        product_name = prod_file.read_text(errors="ignore").strip()
                    break

            if vendor_id == target_vendor.lower() and product_id == target_product.lower() and dev_node.exists():
                return DiscoveredPrinter(
                    device_node=str(dev_node),
                    vendor_id=vendor_id,
                    product_id=product_id,
                    product_name=product_name,
                    writable=os.access(dev_node, os.W_OK),
                )

    # 4. Fallback to first available /dev/usb/lp*
    for candidate in sorted(Path("/dev/usb").glob("lp*")) if Path("/dev/usb").exists() else []:
        return DiscoveredPrinter(
            device_node=str(candidate),
            vendor_id="unknown",
            product_id="unknown",
            product_name="Generic USB Printer",
            writable=os.access(candidate, os.W_OK),
        )

    return None


class PrinterTransport:
    """Thread-safe raw byte transport over USB-to-LPT (/dev/usb/lp0)."""

    def __init__(
        self,
        device_path: str = "auto",
        vendor_id: str = "1a86",
        product_id: str = "7584",
        chunk_size: int = 4096,
        chunk_delay_sec: float = 0.005,
    ) -> None:
        self.device_path = device_path
        self.vendor_id = vendor_id
        self.product_id = product_id
        self.chunk_size = chunk_size
        self.chunk_delay_sec = chunk_delay_sec
        self._lock = threading.Lock()

    def resolve_device(self) -> DiscoveredPrinter:
        """Find the printer device node or raise a descriptive error."""
        info = discover_printer(self.device_path, self.vendor_id, self.product_id)
        if info is None:
            raise FileNotFoundError(
                f"LP2443PSA printer (QinHeng {self.vendor_id}:{self.product_id}) not found. "
                "Verify the USB-to-LPT cable is plugged in."
            )
        if not info.writable:
            raise PermissionError(
                f"Device {info.device_node} is not writable by user '{os.getenv('USER', 'current')}'. "
                f"Run: sudo usermod -aG lp $USER && sudo chmod 666 {info.device_node} "
                "(or run ./deploy/install_pi.sh to install the udev rule)."
            )
        return info

    def send_raw(self, payload: bytes) -> int:
        """Write raw EPL2 bytes to the printer device node in thread-safe chunks."""
        with self._lock:
            info = self.resolve_device()
            logger.info(
                "Sending %d bytes to %s (%s)",
                len(payload),
                info.device_node,
                info.product_name,
            )
            fd = os.open(info.device_node, os.O_WRONLY)
            total_written = 0
            try:
                view = memoryview(payload)
                while total_written < len(payload):
                    chunk = view[total_written : total_written + self.chunk_size]
                    written = os.write(fd, chunk)
                    if written <= 0:
                        raise OSError(f"Write to {info.device_node} returned 0 bytes")
                    total_written += written
                    if total_written < len(payload) and self.chunk_delay_sec > 0:
                        time.sleep(self.chunk_delay_sec)
            finally:
                os.close(fd)
            return total_written
