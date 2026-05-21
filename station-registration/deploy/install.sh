#!/bin/bash
# Instalace registrační stanice na RPi 2GB
set -euo pipefail

INSTALL_DIR="/opt/passport-system"
USER="passport"

echo "[1/5] Systémové balíčky..."
apt update
apt install -y python3-pip python3-venv libnfc6 libnfc-bin

echo "[2/5] Uživatel..."
if ! id -u "$USER" >/dev/null 2>&1; then
    useradd --create-home --shell /bin/bash "$USER"
fi
usermod -a -G plugdev,dialout,i2c "$USER" 2>/dev/null || true

echo "[3/5] Kopírování souborů..."
SOURCE_DIR=$(cd "$(dirname "$0")/../.." && pwd)
mkdir -p "$INSTALL_DIR"
cp -r "$SOURCE_DIR"/shared "$INSTALL_DIR/"
cp -r "$SOURCE_DIR"/station-registration "$INSTALL_DIR/"
chown -R "$USER:$USER" "$INSTALL_DIR"
mkdir -p /var/log/passport
chown "$USER:$USER" /var/log/passport

echo "[4/5] Python venv..."
sudo -u "$USER" python3 -m venv "$INSTALL_DIR/station-registration/.venv"
sudo -u "$USER" "$INSTALL_DIR/station-registration/.venv/bin/pip" install \
    -r "$INSTALL_DIR/station-registration/requirements.txt"

echo "[5/5] Konfigurace + systemd..."
if [ ! -f /boot/station.conf ]; then
    cp "$INSTALL_DIR/station-registration/deploy/station.conf.example" /boot/station.conf
fi
cp "$INSTALL_DIR/station-registration/deploy/passport-registration.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable passport-registration.service
systemctl start passport-registration.service

echo ""
echo "Hotovo! Notebook připoj přes http://<ip-rpi>:8000"
echo "Diagnostika: journalctl -u passport-registration -f"
