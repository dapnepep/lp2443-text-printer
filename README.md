# LP2443PSA Text-to-Label Printer (`lp2443-text-printer`)

Plug-and-play Python application that prints incoming text messages (and photos) onto **4" × 6" thermal shipping labels** using an **Eltron / Zebra LP2443PSA (Orion)** label printer connected via a **QinHeng Electronics CH340S USB-to-LPT (`1a86:7584`)** parallel adapter on a **Raspberry Pi 4** (or any stock Debian Linux machine).

---

## ✨ Features

- **100% Plug-and-Play Hardware Auto-Discovery:** Automatically locates the QinHeng CH340S (`idVendor=1a86`, `idProduct=7584`) via Linux `sysfs` (`/sys/class/usbmisc/lp*`) or persistent `/dev/lp2443` udev symlink.
- **Persistent udev Rule + No Dropped Bytes:** Includes `deploy/99-lp2443-qinheng.rules` to assign `0660` permissions (`lp` group), create `/dev/lp2443`, and disable USB autosuspend (`power/control="on"`).
- **Rich Pillow 13 Label Rendering (`GW` Bitmap Engine):**
  - Renders crisp TrueType fonts with **automatic font scaling** (`110pt` down to `24pt`) so short messages print large and bold while long messages wrap cleanly across the 4" × 6" (`812 × 1218` dots @ 203 DPI) label.
  - Optional sender + timestamp header banner and rounded border.
  - Supports printing photos/images using Floyd-Steinberg 1-bit thermal dithering.
- **Multiple Ways to Text Your Printer:**
  1. **Telegram Bot (Free, Zero Port-Forwarding, Highest Security):** Uses outbound TLS long-polling and restricts access strictly to your numeric Telegram User ID (`LP2443_TELEGRAM_ALLOWED_USER_IDS`).
  2. **Mobile-Friendly Web UI (`http://<pi-ip>:8000`):** Type messages and preview 4×6 labels right from your phone browser over Wi-Fi or Tailscale.
  3. **REST API (`POST /api/print`) & iOS/Android Shortcuts:** Automate printing incoming SMS messages directly from your phone for free.
  4. **Twilio / Telnyx SMS Webhook (`POST /webhook/sms`):** Form-encoded webhook endpoint ready for carrier SMS numbers.

---

## 🚀 Quick Start on Stock Raspberry Pi 4 (Debian Bookworm / Trixie)

Clone the repository and run the one-command installer:

```bash
git clone https://github.com/dapnepep/lp2443-text-printer.git
cd lp2443-text-printer
chmod +x deploy/install_pi.sh
./deploy/install_pi.sh
```

The installer:
1. Installs required Debian packages (`python3-venv`, `fonts-dejavu-core`, `fonts-noto-core`, `usbutils`, `udev`).
2. Installs `/etc/udev/rules.d/99-lp2443-qinheng.rules` and adds your user to the `lp` group.
3. Builds `.venv` and installs the latest PyPI dependencies.
4. Registers and starts the `lp2443-printer.service` systemd unit on boot.

---

## 🛠️ CLI Usage (`lp2443`)

```bash
# 1. Check if the QinHeng 1a86:7584 USB-LPT converter is detected and writable
.venv/bin/lp2443 probe

# 2. Print a 4x6 diagnostic test label
.venv/bin/lp2443 test-print

# 3. Print any custom message from the terminal
.venv/bin/lp2443 print "Pick up coffee and shipping tape!" --sender "Jake"

# 4. Generate a 4x6 PNG preview without printing
.venv/bin/lp2443 preview "Testing layout!" -o preview.png

# 5. Run the Web UI + Webhook + Telegram Bot server manually
.venv/bin/lp2443 serve
```

> **Note on Bitmap Polarity:** If your specific LP2443PSA firmware revision prints inverted (white text on a black label), set `LP2443_INVERT_BITMAP=true` in `.env` or pass `--invert` on the CLI.

---

## 📱 Setting Up Free Texting via Telegram (5 Minutes)

1. Open Telegram and message **[@BotFather](https://t.me/BotFather)** with `/newbot` to get a bot token.
2. Put the token in `.env`:
   ```ini
   LP2443_TELEGRAM_BOT_TOKEN=123456789:ABCDEF...
   ```
3. Send `/start` to your new bot on Telegram. It will reply with your numeric Telegram User ID.
4. Add your ID to `.env` and restart the service:
   ```ini
   LP2443_TELEGRAM_ALLOWED_USER_IDS=987654321
   ```
   ```bash
   sudo systemctl restart lp2443-printer
   ```
5. Any text message or photo you send to your bot will now print immediately!

---

## 🧪 Running Tests & Linter

```bash
make test
make lint
```
