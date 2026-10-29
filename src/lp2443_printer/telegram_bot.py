"""Outbound long-polling Telegram Bot for printing text and photos to the LP2443PSA."""

from __future__ import annotations

import asyncio
import io
import logging

from PIL import Image
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from lp2443_printer.service import PrinterService

logger = logging.getLogger(__name__)


class TelegramPrinterBot:
    """Telegram Bot wrapper that listens via outbound TLS polling and prints incoming messages."""

    def __init__(self, printer_service: PrinterService) -> None:
        self.service = printer_service
        self.allowed_ids = self.service.cfg.get_allowed_telegram_ids()
        self._app: Application | None = None

    def _is_authorized(self, user_id: int | None) -> bool:
        if user_id is None:
            return False
        if not self.allowed_ids:
            # If no IDs are configured yet, allow only if explicitly left open for initial setup
            return False
        return user_id in self.allowed_ids

    async def _cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user
        if not user or not update.message:
            return
        if not self.allowed_ids:
            await update.message.reply_text(
                f"👋 Welcome to LP2443PSA Text Printer!\n\n"
                f"Your numeric Telegram User ID is: `{user.id}`\n\n"
                f"Add `LP2443_TELEGRAM_ALLOWED_USER_IDS={user.id}` to your `.env` file "
                f"and restart the service to authorize printing.",
                parse_mode="Markdown",
            )
            return

        if not self._is_authorized(user.id):
            logger.warning("Unauthorized Telegram access attempt from user_id=%s", user.id)
            await update.message.reply_text("⛔ Unauthorized user ID.")
            return

        await update.message.reply_text(
            "🖨️ *LP2443PSA Printer Bot Ready!*\n\n"
            "Send me any text message (or photo with caption) and I will print it immediately on a 4×6 label.\n"
            "Commands:\n"
            "• `/status` — Check printer hardware status\n"
            "• `/id` — Show your Telegram User ID",
            parse_mode="Markdown",
        )

    async def _cmd_id(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_user and update.message:
            await update.message.reply_text(
                f"Your Telegram User ID is: `{update.effective_user.id}`",
                parse_mode="Markdown",
            )

    async def _cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user
        if not user or not update.message:
            return
        if self.allowed_ids and not self._is_authorized(user.id):
            await update.message.reply_text("⛔ Unauthorized.")
            return

        info = self.service.probe()
        if info is None:
            await update.message.reply_text("⚠️ Printer not detected on USB (`1a86:7584`).")
        else:
            status_icon = "✅ Writable" if info.writable else "🔒 Permission denied (check lp group)"
            await update.message.reply_text(
                f"🖨️ *Printer Detected*\n"
                f"• Device: `{info.device_node}`\n"
                f"• Hardware: `{info.product_name}` (`{info.vendor_id}:{info.product_id}`)\n"
                f"• Access: {status_icon}",
                parse_mode="Markdown",
            )

    async def _handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user
        if not user or not update.message or not update.message.text:
            return

        if not self.allowed_ids:
            await update.message.reply_text(
                f"🔒 Please authorize your User ID first by setting:\n"
                f"`LP2443_TELEGRAM_ALLOWED_USER_IDS={user.id}` in `.env`.",
                parse_mode="Markdown",
            )
            return

        if not self._is_authorized(user.id):
            logger.warning("Unauthorized print attempt from user_id=%s", user.id)
            await update.message.reply_text("⛔ Unauthorized user ID.")
            return

        sender_name = user.first_name or user.username or str(user.id)
        text_body = update.message.text
        try:
            bytes_written = await asyncio.to_thread(
                self.service.print_text,
                message=text_body,
                sender=sender_name,
            )
            await update.message.reply_text(f"✅ Printed on LP2443PSA ({bytes_written:,} bytes sent).")
        except Exception as exc:
            logger.exception("Failed to print Telegram message")
            await update.message.reply_text(f"❌ Print error: {exc}")

    async def _handle_photo(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user
        if not user or not update.message or not update.message.photo:
            return
        if not self._is_authorized(user.id):
            await update.message.reply_text("⛔ Unauthorized user ID.")
            return

        sender_name = user.first_name or user.username or str(user.id)
        caption = update.message.caption or ""
        try:
            photo_file = await update.message.photo[-1].get_file()
            buf = io.BytesIO()
            await photo_file.download_to_memory(out=buf)
            buf.seek(0)
            pil_img = Image.open(buf)
            bytes_written = await asyncio.to_thread(
                self.service.print_image,
                source_image=pil_img,
                caption=caption,
                sender=sender_name,
            )
            await update.message.reply_text(f"🖼️ Photo printed on LP2443PSA ({bytes_written:,} bytes sent).")
        except Exception as exc:
            logger.exception("Failed to print Telegram photo")
            await update.message.reply_text(f"❌ Photo print error: {exc}")

    async def start_background(self) -> None:
        """Start Telegram long-polling in the current asyncio event loop."""
        token = self.service.cfg.telegram_bot_token.strip()
        if not token:
            logger.info("No LP2443_TELEGRAM_BOT_TOKEN configured; Telegram bot polling disabled.")
            return

        self._app = Application.builder().token(token).build()
        self._app.add_handler(CommandHandler("start", self._cmd_start))
        self._app.add_handler(CommandHandler("id", self._cmd_id))
        self._app.add_handler(CommandHandler("status", self._cmd_status))
        self._app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_text))
        self._app.add_handler(MessageHandler(filters.PHOTO, self._handle_photo))

        await self._app.initialize()
        await self._app.start()
        if self._app.updater:
            await self._app.updater.start_polling(drop_pending_updates=True)
        logger.info("Telegram bot polling started (allowed IDs: %s)", self.allowed_ids or "NONE")

    async def stop_background(self) -> None:
        """Stop Telegram long-polling cleanly."""
        if self._app is not None:
            if self._app.updater and self._app.updater.running:
                await self._app.updater.stop()
            if self._app.running:
                await self._app.stop()
            await self._app.shutdown()
            logger.info("Telegram bot polling stopped.")
