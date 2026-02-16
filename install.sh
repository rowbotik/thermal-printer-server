#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FILES_DIR="$SCRIPT_DIR/files"

TARGET_USER="${THERMAL_USER:-alex}"
TARGET_GROUP="${THERMAL_GROUP:-lp}"
SKIP_APT=0

usage() {
  cat <<'EOF'
Usage: sudo ./install.sh [--user <name>] [--group <name>] [--skip-apt]

Installs the thermal printer stack using the exact snapshot from this bundle.

Options:
  --user <name>    Service user to run print server (default: alex)
  --group <name>   Service group (default: lp)
  --skip-apt       Skip apt package installation
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --user)
      TARGET_USER="$2"
      shift 2
      ;;
    --group)
      TARGET_GROUP="$2"
      shift 2
      ;;
    --skip-apt)
      SKIP_APT=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 1
      ;;
  esac
done

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root (e.g., sudo ./install.sh)." >&2
  exit 1
fi

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "Missing required command: $1" >&2
    exit 1
  }
}

backup_file() {
  local path="$1"
  if [[ -f "$path" ]]; then
    cp "$path" "${path}.bak.$(date +%Y%m%d-%H%M%S)"
  fi
}

echo "[1/9] Validating prerequisites..."
require_cmd install
require_cmd systemctl
require_cmd lpadmin
require_cmd lpoptions
require_cmd curl

if ! id "$TARGET_USER" >/dev/null 2>&1; then
  echo "User '$TARGET_USER' does not exist on this machine." >&2
  exit 1
fi

if [[ "$SKIP_APT" -eq 0 ]]; then
  echo "[2/9] Installing packages..."
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -y
  apt-get install -y cups cups-client poppler-utils curl python3-pil
else
  echo "[2/9] Skipping apt package install (--skip-apt)."
fi

echo "[3/9] Creating directories..."
install -d -m 0755 /opt/thermal-printer
install -d -m 0755 /usr/lib/cups/backend
install -d -m 0755 /usr/lib/cups/filter
install -d -m 0755 /etc/cups/ppd

echo "[4/9] Backing up existing files..."
backup_file /opt/thermal-printer/print_server.py
backup_file /usr/lib/cups/backend/pdf2http
backup_file /usr/lib/cups/filter/pdftopdf2http
backup_file /etc/cups/ppd/thermal.ppd
backup_file /etc/systemd/system/thermal-printer.service

echo "[5/9] Installing snapshot files..."
install -m 0755 "$FILES_DIR/opt/thermal-printer/print_server.py" /opt/thermal-printer/print_server.py
install -m 0755 "$FILES_DIR/usr/lib/cups/backend/pdf2http" /usr/lib/cups/backend/pdf2http
install -m 0755 "$FILES_DIR/usr/lib/cups/filter/pdftopdf2http" /usr/lib/cups/filter/pdftopdf2http
install -m 0644 "$FILES_DIR/etc/systemd/system/thermal-printer.service" /etc/systemd/system/thermal-printer.service
install -m 0640 "$FILES_DIR/etc/cups/ppd/thermal.ppd" /etc/cups/ppd/thermal.ppd

chown "$TARGET_USER:$TARGET_USER" /opt/thermal-printer/print_server.py
chown root:root /usr/lib/cups/backend/pdf2http
chown root:root /usr/lib/cups/filter/pdftopdf2http
chown root:root /etc/systemd/system/thermal-printer.service
chown root:lp /etc/cups/ppd/thermal.ppd

echo "[6/9] Applying service user/group..."
sed -i "s/^User=.*/User=$TARGET_USER/" /etc/systemd/system/thermal-printer.service
sed -i "s/^Group=.*/Group=$TARGET_GROUP/" /etc/systemd/system/thermal-printer.service
usermod -a -G lp "$TARGET_USER" || true

echo "[7/9] Configuring services..."
systemctl daemon-reload
systemctl enable --now cups
systemctl restart cups

# Avoid stale manual process binding to :8765
pkill -f '/opt/thermal-printer/print_server.py' || true

systemctl enable --now thermal-printer.service
systemctl restart thermal-printer.service

echo "[8/9] Configuring CUPS queue..."
lpadmin -x thermal 2>/dev/null || true
lpadmin -p thermal -E -v pdf2http://localhost:8765 -P /etc/cups/ppd/thermal.ppd
lpadmin -d thermal
lpadmin -p thermal -o printer-is-shared=true
lpoptions -p thermal -o PageSize=Roll4x6
lpoptions -p thermal -o Resolution=203dpi

echo "[9/9] Running alignment home command..."
curl -fsS -X POST http://localhost:8765/raw \
  --data-binary $'SIZE 101.6mm,152.4mm\nGAP 3mm,0mm\nGAPDETECT\nHOME\n' >/dev/null

echo
echo "Install complete."
echo "Quick status:"
systemctl --no-pager --full status thermal-printer.service | sed -n '1,14p'
echo "---"
lpstat -d
lpstat -v | sed -n '1,4p'
echo "---"
curl -s http://localhost:8765/ | sed -n '1,6p'
