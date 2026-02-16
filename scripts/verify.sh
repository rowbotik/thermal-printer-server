#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root (e.g., sudo ./scripts/verify.sh)." >&2
  exit 1
fi

echo "Service status:"
systemctl is-active thermal-printer.service
systemctl is-enabled thermal-printer.service
echo "---"

echo "CUPS status:"
lpstat -d
lpstat -v
echo "---"

echo "Thermal API banner:"
curl -fsS http://localhost:8765/ | sed -n '1,8p'
echo "---"

echo "Queue options:"
lpoptions -p thermal
echo
echo "Verification completed."
