#!/usr/bin/env bash
# ============================================================================
# Plug-and-Play Installer for Stock Debian / Raspberry Pi OS (RPi 4)
# Configures udev rules for QinHeng 1a86:7584, system fonts, Python venv,
# and registers the systemd background service.
# ============================================================================
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET_USER="${SUDO_USER:-$(whoami)}"

echo "=== [1/5] Installing required Debian packages (Python, TrueType Fonts, udev) ==="
sudo apt-get update
sudo apt-get install -y \
    python3 \
    python3-venv \
    python3-pip \
    fonts-dejavu-core \
    fonts-noto-core \
    fonts-noto-mono \
    usbutils \
    udev \
    git

echo "=== [2/5] Installing udev rule for QinHeng CH340S (1a86:7584 -> /dev/lp2443) ==="
sudo cp "${REPO_DIR}/deploy/99-lp2443-qinheng.rules" /etc/udev/rules.d/99-lp2443-qinheng.rules
sudo usermod -aG lp "${TARGET_USER}"
sudo udevadm control --reload-rules
sudo udevadm trigger

if [ -e /dev/usb/lp0 ]; then
    sudo chgrp lp /dev/usb/lp0 || true
    sudo chmod 660 /dev/usb/lp0 || true
fi

echo "=== [3/5] Creating Python virtual environment and installing latest packages ==="
cd "${REPO_DIR}"
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -e ".[dev]"

if [ ! -f "${REPO_DIR}/.env" ]; then
    cp "${REPO_DIR}/.env.example" "${REPO_DIR}/.env"
    echo "Created default .env from .env.example"
fi

echo "=== [4/5] Installing and enabling systemd service (lp2443-printer.service) ==="
SERVICE_TMP="$(mktemp)"
sed -e "s|__SERVICE_USER__|${TARGET_USER}|g" \
    -e "s|__INSTALL_DIR__|${REPO_DIR}|g" \
    "${REPO_DIR}/deploy/lp2443-printer.service" > "${SERVICE_TMP}"

sudo mv "${SERVICE_TMP}" /etc/systemd/system/lp2443-printer.service
sudo chmod 644 /etc/systemd/system/lp2443-printer.service
sudo systemctl daemon-reload
sudo systemctl enable lp2443-printer.service
sudo systemctl restart lp2443-printer.service

echo "=== [5/5] Verifying printer detection ==="
.venv/bin/lp2443 probe || true

echo ""
echo "✅ Plug-and-play installation complete!"
echo "   • Web UI      : http://$(hostname -I | awk '{print $1}'):8000"
echo "   • Config file : ${REPO_DIR}/.env"
echo "   • Logs        : sudo journalctl -u lp2443-printer -f"
