"""Configuration management using pydantic-settings."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class PrinterSettings(BaseSettings):
    """Settings for the LP2443PSA printer and messaging interfaces."""

    model_config = SettingsConfigDict(
        env_prefix="LP2443_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Hardware / USB-LPT settings
    device_path: str = Field(
        default="auto",
        description="Device path ('auto', '/dev/lp2443', '/dev/usb/lp0', or a file path for dry-run)",
    )
    usb_vendor_id: str = Field(default="1a86", description="QinHeng USB Vendor ID")
    usb_product_id: str = Field(default="7584", description="CH340S USB-LPT Product ID")

    # Label geometry in dots (203 DPI: 4" = 812 dots, 6" = 1218 dots, gap = 24 dots)
    label_width_dots: int = Field(default=812, ge=100, le=832)
    label_height_dots: int = Field(default=1218, ge=100, le=2200)
    gap_dots: int = Field(default=24, ge=0, le=120)

    # EPL2 print parameters
    speed: int = Field(default=1, ge=1, le=4, description="Print speed (1-4 for LP2443; 1=slowest/darkest)")
    density: int = Field(default=15, ge=0, le=15, description="Print darkness/density (0-15; 15=maximum darkness)")
    invert_bitmap: bool = Field(
        default=False,
        description="Invert GW bitmap bits if firmware expects 1=black instead of 0=black",
    )

    # HTTP / Webhook Server settings
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8000, ge=1, le=65535)
    api_key: str = Field(default="", description="Optional API key for HTTP/Webhook endpoints")

    # Telegram Bot settings
    telegram_bot_token: str = Field(default="", description="Telegram Bot Token from @BotFather")
    telegram_allowed_user_ids: str = Field(
        default="",
        description="Comma-separated numeric Telegram user IDs allowed to print",
    )

    def get_allowed_telegram_ids(self) -> set[int]:
        """Parse comma-separated Telegram user IDs into a set of ints."""
        if not self.telegram_allowed_user_ids.strip():
            return set()
        result: set[int] = set()
        for part in self.telegram_allowed_user_ids.split(","):
            cleaned = part.strip()
            if cleaned.isdigit():
                result.add(int(cleaned))
        return result


settings = PrinterSettings()
