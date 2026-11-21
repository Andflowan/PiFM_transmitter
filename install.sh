#!/usr/bin/env bash
# PiFM_transmitter installer. Usage: sudo ./install.sh [--samba]
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then echo "Please run with sudo:  sudo ./install.sh"; exit 1; fi

case "$(uname -m)" in
  armv6l|armv7l) ;;
  *) echo "ERROR: a 32-bit Raspberry Pi OS is required (uname -m shows '$(uname -m)')."
     echo "PiFmRds does not work on 64-bit systems. Re-flash 'Raspberry Pi OS Lite (32-bit)'."; exit 1 ;;
esac
if grep -q "Raspberry Pi 5" /proc/device-tree/model 2>/dev/null; then
  echo "ERROR: the Raspberry Pi 5 is not supported by PiFmRds."; exit 1
fi
FREE=$(df --output=avail -m / | tail -1 | tr -d ' ')
if [ "$FREE" -lt 400 ]; then
  echo "ERROR: only ${FREE} MB free on /. Use a bigger SD card (8 GB or more recommended)."; exit 1
fi

INSTALL=/opt/PiFM_transmitter
SRC="$(cd "$(dirname "$0")" && pwd)"
RUN_USER="${SUDO_USER:-root}"

echo "==> Installing packages"
apt-get update
apt-get install -y python3-flask ffmpeg git make gcc libsndfile1-dev

echo "==> Installing app to $INSTALL"
mkdir -p "$INSTALL/playlists/Main"
cp "$SRC/app.py" "$SRC/index.html" "$INSTALL/"

echo "==> Building PiFmRds"
if [ ! -d "$INSTALL/PiFmRds" ]; then
  git clone https://github.com/ChristopheJacquet/PiFmRds.git "$INSTALL/PiFmRds"
fi
make -C "$INSTALL/PiFmRds/src" clean
make -C "$INSTALL/PiFmRds/src"

echo "==> Creating systemd service"
cat > /etc/systemd/system/PiFM_transmitter.service <<UNIT
[Unit]
Description=PiFM_transmitter
After=network-online.target
Wants=network-online.target

[Service]
WorkingDirectory=$INSTALL
Environment=PIFM=$INSTALL/PiFmRds/src/pi_fm_rds
Environment=PORT=80
ExecStart=/usr/bin/python3 $INSTALL/app.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable PiFM_transmitter
systemctl restart PiFM_transmitter

if [ "${1:-}" = "--samba" ]; then
  echo "==> Setting up the Samba share"
  apt-get install -y --no-install-recommends samba
  if ! grep -q "^\[playlists\]" /etc/samba/smb.conf; then
    cat >> /etc/samba/smb.conf <<SMB

[playlists]
   path = $INSTALL/playlists
   writeable = yes
   browseable = yes
   valid users = $RUN_USER
   force user = root
   create mask = 0664
   directory mask = 0775
SMB
  fi
  echo "Choose a password for the network share (user: $RUN_USER):"
  smbpasswd -a "$RUN_USER"
  systemctl restart smbd
fi

IP=$(hostname -I | awk '{print $1}')
echo
echo "Done! Open  http://$IP  in a browser on the same network."
echo "Antenna: a ~20 cm wire on physical pin 7 (GPIO 4). Default frequency: 99.9 MHz."
