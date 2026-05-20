#!/bin/bash
# Instalace stanice země na RPi
# Spusť jako root: sudo bash install.sh

set -euo pipefail

INSTALL_DIR="/opt/passport-system"
USER="passport"

echo "[1/7] Systémové balíčky..."
apt update
apt install -y python3-pip python3-venv chromium-browser \
    xserver-xorg xinit \
    libnfc6 libnfc-bin libnfc-pn53x-examples \
    unclutter

echo "[2/7] Uživatel..."
if ! id -u "$USER" >/dev/null 2>&1; then
    useradd --create-home --shell /bin/bash "$USER"
fi
usermod -a -G plugdev,dialout,i2c,gpio,video,input "$USER" 2>/dev/null || true

echo "[3/7] Kopírování souborů..."
SOURCE_DIR=$(cd "$(dirname "$0")/../.." && pwd)
mkdir -p "$INSTALL_DIR"
cp -r "$SOURCE_DIR"/shared "$INSTALL_DIR/"
cp -r "$SOURCE_DIR"/station-country "$INSTALL_DIR/"
chown -R "$USER:$USER" "$INSTALL_DIR"
mkdir -p /var/log/passport
chown "$USER:$USER" /var/log/passport

echo "[4/7] Python venv..."
sudo -u "$USER" python3 -m venv "$INSTALL_DIR/station-country/.venv"
sudo -u "$USER" "$INSTALL_DIR/station-country/.venv/bin/pip" install \
    -r "$INSTALL_DIR/station-country/requirements.txt"

echo "[5/7] station.conf..."
if [ ! -f /boot/station.conf ]; then
    cp "$INSTALL_DIR/station-country/deploy/station.conf.example" /boot/station.conf
    echo ""
    echo "!! POZOR: /boot/station.conf vytvořen z výchozího vzoru."
    echo "!! UPRAV ho a nastav COUNTRY_INDEX (0-10) podle této stanice !!"
    echo ""
fi

echo "[6/7] Asety placeholderů (pokud nejsou)..."
if [ ! -f "$INSTALL_DIR/station-country/frontend/assets/logo.svg" ]; then
    sudo -u "$USER" "$INSTALL_DIR/station-country/.venv/bin/python" \
        "$INSTALL_DIR/station-country/scripts/generate_assets.py" \
        "$INSTALL_DIR/station-country/frontend/assets"
fi

echo "[7/7] systemd..."
cp "$INSTALL_DIR/station-country/deploy/passport-station.service" /etc/systemd/system/
cp "$INSTALL_DIR/station-country/deploy/passport-kiosk.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable passport-station.service
systemctl enable passport-kiosk.service

# Automatický boot do GUI s passport uživatelem
raspi-config nonint do_boot_behaviour B4 2>/dev/null || true

echo ""
echo "==================================================="
echo "Hotovo!"
echo ""
echo "1. UPRAV /boot/station.conf - nastav COUNTRY_INDEX"
echo "2. Restartuj RPi: sudo reboot"
echo ""
echo "Po restartu by mělo automaticky:"
echo "  - nastartovat daemon (passport-station.service)"
echo "  - nastartovat Chromium kiosk"
echo ""
echo "Diagnostika:"
echo "  systemctl status passport-station"
echo "  journalctl -u passport-station -f"
echo "  curl localhost:8090/health"
echo "==================================================="
