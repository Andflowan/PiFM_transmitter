#!/usr/bin/env bash
# Removes the service. Your music in /opt/PiFM_transmitter/playlists is kept unless you pass --purge.
set -e
[ "$(id -u)" -eq 0 ] || { echo "Run with sudo"; exit 1; }
systemctl disable --now PiFM_transmitter 2>/dev/null || true
rm -f /etc/systemd/system/PiFM_transmitter.service
systemctl daemon-reload
pkill pi_fm_rds 2>/dev/null || true
if [ "${1:-}" = "--purge" ]; then rm -rf /opt/PiFM_transmitter; echo "Everything removed."; else echo "Service removed. Music kept in /opt/PiFM_transmitter/playlists."; fi
