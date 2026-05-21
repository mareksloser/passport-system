#!/bin/bash
# Instalace pokladny na RPi 1GB
set -euo pipefail

INSTALL_DIR="/opt/passport-system"
USER="passport"

echo "[1/6] Systémové balíčky..."
apt update
apt install -y python3-pip python3-venv chromium-browser \
    libnfc6 libnfc-bin unclutter

echo "[2/6] Uživatel..."
if ! id -u "$USER" >/dev/null 2>&1; then
    useradd --create-home --shell /bin/bash "$USER"
fi
usermod -a -G plugdev,dialout,i2c,gpio,video,input "$USER" 2>/dev/null || true

echo "[3/6] Kopírování souborů..."
SOURCE_DIR=$(cd "$(dirname "$0")/../.." && pwd)
mkdir -p "$INSTALL_DIR"
cp -r "$SOURCE_DIR"/shared "$INSTALL_DIR/"
cp -r "$SOURCE_DIR"/station-checkout "$INSTALL_DIR/"
chown -R "$USER:$USER" "$INSTALL_DIR"
mkdir -p /var/log/passport
chown "$USER:$USER" /var/log/passport

echo "[4/6] Python venv..."
sudo -u "$USER" python3 -m venv "$INSTALL_DIR/station-checkout/.venv"
sudo -u "$USER" "$INSTALL_DIR/station-checkout/.venv/bin/pip" install \
    -r "$INSTALL_DIR/station-checkout/requirements.txt"

echo "[5/6] Konfigurace..."
if [ ! -f /boot/station.conf ]; then
    cp "$INSTALL_DIR/station-checkout/deploy/station.conf.example" /boot/station.conf
    echo "!! UPRAV /boot/station.conf - hlavně CHECKPOINT_LABEL (např. 'Pokladna 1')"
fi

echo "[6/6] systemd..."
cp "$INSTALL_DIR/station-checkout/deploy/passport-checkout.service" /etc/systemd/system/
cp "$INSTALL_DIR/station-checkout/deploy/passport-kiosk.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable passport-checkout.service
systemctl enable passport-kiosk.service

raspi-config nonint do_boot_behaviour B4 2>/dev/null || true

echo ""
echo "==================================================="
echo "Hotovo! Po restartu RPi se pokladna spustí automaticky."
echo ""
echo "Diagnostika:"
echo "  systemctl status passport-checkout"
echo "  journalctl -u passport-checkout -f"
echo "  curl localhost:8090/health"
echo "==================================================="
