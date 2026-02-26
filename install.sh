#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FILES_DIR="$SCRIPT_DIR/files"

TARGET_USER="${THERMAL_USER:-alex}"
TARGET_GROUP="${THERMAL_GROUP:-lp}"
SKIP_APT=0
ENABLE_REMOTE_CUPS=0
ENABLE_CUPS_ADMIN=0

usage() {
  cat <<'EOF'
Usage: sudo ./install.sh [--user <name>] [--group <name>] [--skip-apt] [--enable-remote-cups] [--enable-cups-admin]

Installs the thermal printer stack using the exact snapshot from this bundle.

Options:
  --user <name>    Service user to run print server (default: alex)
  --group <name>   Service group (default: lp)
  --skip-apt       Skip apt package installation
  --enable-remote-cups   Enable remote IPP access + printer sharing in CUPS
  --enable-cups-admin    Enable remote CUPS admin UI access (implies --enable-remote-cups)
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
    --enable-remote-cups)
      ENABLE_REMOTE_CUPS=1
      shift
      ;;
    --enable-cups-admin)
      ENABLE_CUPS_ADMIN=1
      ENABLE_REMOTE_CUPS=1
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

warn() {
  echo "WARN: $*" >&2
}

backup_file() {
  local path="$1"
  if [[ -f "$path" ]]; then
    cp "$path" "${path}.bak.$(date +%Y%m%d-%H%M%S)"
  fi
}

detect_printer_device() {
  local candidate
  for candidate in /dev/thermal-printer /dev/usb/lp0 /dev/usb/lp1 /dev/usb/lp2; do
    if [[ -e "$candidate" ]]; then
      echo "$candidate"
      return 0
    fi
  done
  return 1
}

run_alignment_home() {
  local response_file http_code
  response_file="$(mktemp)"
  trap 'rm -f "$response_file"' RETURN

  http_code="$(
    curl -sS -o "$response_file" -w '%{http_code}' -X POST http://localhost:8765/raw \
      --data-binary $'SIZE 101.6mm,152.4mm\nGAP 3mm,0mm\nGAPDETECT\nHOME\n' || true
  )"

  if [[ "$http_code" =~ ^2 ]]; then
    echo "Alignment command sent successfully."
    return 0
  fi

  warn "Alignment command skipped/failed (HTTP ${http_code:-curl-error})."
  if [[ -s "$response_file" ]]; then
    warn "Thermal API response: $(tr '\n' ' ' < "$response_file")"
  fi
  return 0
}

echo "[1/9] Validating prerequisites..."
require_cmd install
require_cmd systemctl
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

# These are provided by cups-client/cups and may not exist before apt install
# on a fresh machine.
require_cmd lpadmin
require_cmd lpoptions
if [[ "$ENABLE_REMOTE_CUPS" -eq 1 || "$ENABLE_CUPS_ADMIN" -eq 1 ]]; then
  require_cmd cupsctl
fi

echo "[3/9] Creating directories..."
install -d -m 0755 /opt/thermal-printer
install -d -m 0755 /usr/lib/cups/backend
install -d -m 0755 /usr/lib/cups/filter
install -d -m 0755 /etc/cups/ppd
install -d -m 0755 /etc/udev/rules.d

echo "[4/9] Backing up existing files..."
backup_file /opt/thermal-printer/print_server.py
backup_file /usr/lib/cups/backend/pdf2http
backup_file /usr/lib/cups/filter/pdftopdf2http
backup_file /etc/cups/ppd/thermal.ppd
backup_file /etc/systemd/system/thermal-printer.service
backup_file /etc/udev/rules.d/99-thermal-printer.rules

echo "[5/9] Installing snapshot files..."
install -m 0755 "$FILES_DIR/opt/thermal-printer/print_server.py" /opt/thermal-printer/print_server.py
install -m 0755 "$FILES_DIR/usr/lib/cups/backend/pdf2http" /usr/lib/cups/backend/pdf2http
install -m 0755 "$FILES_DIR/usr/lib/cups/filter/pdftopdf2http" /usr/lib/cups/filter/pdftopdf2http
install -m 0644 "$FILES_DIR/etc/systemd/system/thermal-printer.service" /etc/systemd/system/thermal-printer.service
install -m 0640 "$FILES_DIR/etc/cups/ppd/thermal.ppd" /etc/cups/ppd/thermal.ppd
if [[ -f "$FILES_DIR/etc/udev/rules.d/99-thermal-printer.rules" ]]; then
  install -m 0644 "$FILES_DIR/etc/udev/rules.d/99-thermal-printer.rules" /etc/udev/rules.d/99-thermal-printer.rules
fi

chown "$TARGET_USER:$TARGET_USER" /opt/thermal-printer/print_server.py
chown root:root /usr/lib/cups/backend/pdf2http
chown root:root /usr/lib/cups/filter/pdftopdf2http
chown root:root /etc/systemd/system/thermal-printer.service
chown root:lp /etc/cups/ppd/thermal.ppd
[[ -f /etc/udev/rules.d/99-thermal-printer.rules ]] && chown root:root /etc/udev/rules.d/99-thermal-printer.rules

echo "[6/9] Applying service user/group..."
sed -i "s/^User=.*/User=$TARGET_USER/" /etc/systemd/system/thermal-printer.service
sed -i "s/^Group=.*/Group=$TARGET_GROUP/" /etc/systemd/system/thermal-printer.service
usermod -a -G lp "$TARGET_USER" || true
if getent group lpadmin >/dev/null 2>&1; then
  usermod -a -G lpadmin "$TARGET_USER" || true
fi

echo "[7/9] Configuring services..."
systemctl daemon-reload
systemctl enable --now cups
systemctl restart cups
if command -v udevadm >/dev/null 2>&1 && [[ -f /etc/udev/rules.d/99-thermal-printer.rules ]]; then
  udevadm control --reload-rules || true
  udevadm trigger /dev/usb/lp0 2>/dev/null || true
fi

# Avoid stale manual process binding to :8765
pkill -f '/opt/thermal-printer/print_server.py' || true

systemctl enable --now thermal-printer.service
systemctl restart thermal-printer.service

echo "[8/9] Configuring CUPS queue..."
lpadmin -x thermal 2>/dev/null || true
# Use the snapshot source PPD here because deleting/recreating the queue can
# remove /etc/cups/ppd/thermal.ppd during upgrades.
lpadmin -p thermal -E -v pdf2http://localhost:8765 -P "$FILES_DIR/etc/cups/ppd/thermal.ppd"
lpadmin -d thermal
lpadmin -p thermal -o printer-is-shared=true
lpoptions -p thermal -o PageSize=Roll4x6
lpoptions -p thermal -o Resolution=203dpi

if [[ "$ENABLE_REMOTE_CUPS" -eq 1 ]]; then
  echo "Enabling remote CUPS/IPP access..."
  cupsctl --share-printers --remote-any
  if [[ "$ENABLE_CUPS_ADMIN" -eq 1 ]]; then
    cupsctl --remote-admin
  fi
  systemctl restart cups
fi

echo "[9/9] Running alignment home command..."
if PRINTER_DEVICE="$(detect_printer_device)"; then
  echo "Printer device detected: $PRINTER_DEVICE"
  run_alignment_home
else
  warn "No printer device found (/dev/thermal-printer or /dev/usb/lp*). Skipping alignment."
fi

echo
echo "Install complete."
echo "Quick status:"
systemctl --no-pager --full status thermal-printer.service | sed -n '1,14p'
echo "---"
lpstat -d
lpstat -v | sed -n '1,4p'
echo "---"
curl -s http://localhost:8765/ | sed -n '1,6p'
echo "---"
curl -s http://localhost:8765/healthz | sed -n '1,20p'
