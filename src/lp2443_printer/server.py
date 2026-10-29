"""FastAPI server providing a Mobile Web UI, REST API (/api/print), Live Preview, and SMS Webhook."""

from __future__ import annotations

import asyncio
import io
import secrets
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, Form, Header, HTTPException, Query, status
from fastapi.responses import HTMLResponse, PlainTextResponse, Response
from pydantic import BaseModel, Field

from lp2443_printer.config import PrinterSettings, settings
from lp2443_printer.service import PrinterService
from lp2443_printer.telegram_bot import TelegramPrinterBot


class PrintRequest(BaseModel):
    """JSON request schema for `/api/print`."""

    message: str = Field(..., min_length=1, max_length=4000, description="Text message to print")
    sender: str = Field(default="", max_length=80, description="Optional sender name")
    show_header: bool = Field(default=True, description="Include sender/timestamp banner")
    show_border: bool = Field(default=True, description="Include rounded outer border")
    copies: int = Field(default=1, ge=1, le=10, description="Number of copies to print")


class PrintResponse(BaseModel):
    """JSON response schema for `/api/print`."""

    ok: bool
    bytes_written: int
    device_node: str


WEB_UI_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>LP2443PSA Label Messenger</title>
  <style>
    :root {
      --bg: #0f172a;
      --card: #1e293b;
      --accent: #38bdf8;
      --text: #f8fafc;
      --muted: #94a3b8;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0; padding: 20px;
      font-family: system-ui, -apple-system, sans-serif;
      background: var(--bg); color: var(--text);
      display: flex; justify-content: center;
    }
    .container {
      width: 100%; max-width: 540px;
      background: var(--card); border-radius: 16px;
      padding: 24px; box-shadow: 0 10px 30px rgba(0,0,0,0.4);
    }
    h1 { margin: 0 0 6px; font-size: 1.4rem; }
    .sub { color: var(--muted); font-size: 0.9rem; margin-bottom: 18px; }
    label { display: block; font-size: 0.85rem; color: var(--muted); margin: 12px 0 6px; }
    input[type="text"], input[type="password"], textarea {
      width: 100%; padding: 12px; border-radius: 10px;
      border: 1px solid #334155; background: #0f172a; color: var(--text);
      font-size: 1rem;
    }
    textarea { min-height: 120px; resize: vertical; }
    .row { display: flex; gap: 12px; align-items: center; margin-top: 12px; flex-wrap: wrap; }
    .btn {
      flex: 1; padding: 14px; border: none; border-radius: 10px;
      font-size: 1rem; font-weight: 600; cursor: pointer;
    }
    .btn-primary { background: var(--accent); color: #0f172a; }
    .btn-secondary { background: #334155; color: var(--text); }
    #status { margin-top: 14px; font-size: 0.92rem; }
    .preview-box {
      margin-top: 18px; text-align: center;
      background: #0f172a; padding: 12px; border-radius: 12px;
      display: none;
    }
    .preview-box img {
      max-width: 100%; height: auto; border-radius: 6px; border: 1px solid #475569;
    }
  </style>
</head>
<body>
  <div class="container">
    <h1>🖨️ LP2443PSA Label Messenger</h1>
    <div class="sub">4&quot; × 6&quot; Direct Thermal Label Printer (QinHeng CH340S)</div>

    <label for="sender">From / Header (optional)</label>
    <input id="sender" type="text" placeholder="Jake" />

    <label for="message">Message to Print</label>
    <textarea id="message" placeholder="Type your message here..."></textarea>

    <label for="apikey">API Key (only if configured in .env)</label>
    <input id="apikey" type="password" placeholder="Optional API key" />

    <div class="row">
      <label><input type="checkbox" id="show_header" checked /> Show Header</label>
      <label><input type="checkbox" id="show_border" checked /> Show Border</label>
    </div>

    <div class="row">
      <button class="btn btn-secondary" type="button" onclick="previewLabel()">👁️ Preview 4×6</button>
      <button class="btn btn-primary" type="button" onclick="sendPrint()">🖨️ Print Label</button>
    </div>

    <div id="status"></div>
    <div class="preview-box" id="previewBox">
      <img id="previewImg" alt="Label preview" />
    </div>
  </div>

  <script>
    async function previewLabel() {
      const msg = document.getElementById('message').value || 'Hello World!';
      const sender = document.getElementById('sender').value;
      const hdr = document.getElementById('show_header').checked;
      const bdr = document.getElementById('show_border').checked;
      const params = new URLSearchParams({ message: msg, sender: sender, show_header: hdr, show_border: bdr });
      const box = document.getElementById('previewBox');
      const img = document.getElementById('previewImg');
      img.src = '/api/preview?' + params.toString() + '&_t=' + Date.now();
      box.style.display = 'block';
    }

    async function sendPrint() {
      const statusEl = document.getElementById('status');
      const msg = document.getElementById('message').value.trim();
      if (!msg) {
        statusEl.textContent = '⚠️ Please enter a message to print.';
        return;
      }
      statusEl.textContent = '⏳ Sending to LP2443PSA...';
      const headers = { 'Content-Type': 'application/json' };
      const apiKey = document.getElementById('apikey').value.trim();
      if (apiKey) headers['X-API-Key'] = apiKey;

      try {
        const res = await fetch('/api/print', {
          method: 'POST',
          headers,
          body: JSON.stringify({
            message: msg,
            sender: document.getElementById('sender').value.trim(),
            show_header: document.getElementById('show_header').checked,
            show_border: document.getElementById('show_border').checked,
            copies: 1
          })
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Print failed');
        statusEl.textContent = `✅ Printed! (${data.bytes_written.toLocaleString()} bytes -> ${data.device_node})`;
        document.getElementById('message').value = '';
      } catch (err) {
        statusEl.textContent = '❌ Error: ' + err.message;
      }
    }
  </script>
</body>
</html>
"""


def create_app(custom_settings: PrinterSettings | None = None) -> FastAPI:
    """Create and configure the FastAPI application."""
    cfg = custom_settings or settings
    printer_service = PrinterService(cfg)
    tg_bot = TelegramPrinterBot(printer_service)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await tg_bot.start_background()
        try:
            yield
        finally:
            await tg_bot.stop_background()

    app = FastAPI(
        title="LP2443PSA Text-to-Label Printer Service",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.printer_service = printer_service

    def verify_api_key(
        x_api_key: Annotated[str | None, Header()] = None,
        token: Annotated[str | None, Query()] = None,
    ) -> None:
        expected = cfg.api_key.strip()
        if not expected:
            return
        provided = (x_api_key or token or "").strip()
        if not provided or not secrets.compare_digest(provided, expected):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or missing API key (provide X-API-Key header or ?token= query param)",
            )

    @app.get("/", response_class=HTMLResponse)
    async def index() -> str:
        return WEB_UI_HTML

    @app.get("/api/status")
    async def get_status() -> dict[str, object]:
        info = printer_service.probe()
        if info is None:
            return {
                "connected": False,
                "device_node": None,
                "writable": False,
                "label_size_dots": [cfg.label_width_dots, cfg.label_height_dots],
            }
        return {
            "connected": True,
            "device_node": info.device_node,
            "vendor_id": info.vendor_id,
            "product_id": info.product_id,
            "product_name": info.product_name,
            "writable": info.writable,
            "label_size_dots": [cfg.label_width_dots, cfg.label_height_dots],
        }

    @app.get("/api/preview")
    async def preview_label(
        message: str = Query(default="Hello from LP2443PSA!", max_length=4000),
        sender: str = Query(default="", max_length=80),
        show_header: bool = Query(default=True),
        show_border: bool = Query(default=True),
    ) -> Response:
        img = await asyncio.to_thread(
            printer_service.render_message,
            message=message,
            sender=sender,
            show_header=show_header,
            show_border=show_border,
        )
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return Response(content=buf.getvalue(), media_type="image/png")

    @app.post("/api/print", response_model=PrintResponse, dependencies=[Depends(verify_api_key)])
    async def api_print(req: PrintRequest) -> PrintResponse:
        try:
            info = printer_service.transport.resolve_device()
            bytes_written = await asyncio.to_thread(
                printer_service.print_text,
                message=req.message,
                sender=req.sender,
                show_header=req.show_header,
                show_border=req.show_border,
                copies=req.copies,
            )
            return PrintResponse(
                ok=True,
                bytes_written=bytes_written,
                device_node=info.device_node,
            )
        except FileNotFoundError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Print failed: {exc}") from exc

    @app.post("/webhook/sms", response_class=PlainTextResponse, dependencies=[Depends(verify_api_key)])
    async def twilio_sms_webhook(
        Body: Annotated[str, Form()] = "",
        From: Annotated[str, Form()] = "",
    ) -> Response:
        """Twilio / VoIP / Telnyx compatible form-encoded SMS webhook."""
        if not Body.strip():
            raise HTTPException(status_code=400, detail="Empty SMS Body")
        try:
            await asyncio.to_thread(
                printer_service.print_text,
                message=Body.strip(),
                sender=From.strip() or "SMS",
            )
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"SMS Print error: {exc}") from exc

        twiml = '<?xml version="1.0" encoding="UTF-8"?><Response></Response>'
        return Response(content=twiml, media_type="application/xml")

    return app


app = create_app()
