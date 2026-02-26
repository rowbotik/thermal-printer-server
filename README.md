# Thermal Printer Deploy Snapshot

This bundle installs the current live thermal printer stack from `thermal` (Raspberry Pi), including:

- `/opt/thermal-printer/print_server.py`
- `/usr/lib/cups/backend/pdf2http`
- `/usr/lib/cups/filter/pdftopdf2http`
- `/etc/systemd/system/thermal-printer.service`
- `/etc/cups/ppd/thermal.ppd`

It also configures CUPS queue `thermal` to use `pdf2http://localhost:8765` and sets default media to `Roll4x6`.

## Install On Pi Zero 2

1. Copy this folder to the Pi Zero 2.
2. Run:

```bash
cd deploy-snapshot
chmod +x install.sh scripts/verify.sh
sudo ./install.sh --user alex --group lp --enable-remote-cups --enable-cups-admin
sudo ./scripts/verify.sh
```

If your user is not `alex`, set `--user <your_user>`.

### Installer Flags

```bash
sudo ./install.sh \
  --user alex \
  --group lp \
  --skip-apt \
  --enable-remote-cups \
  --enable-cups-admin
```

- `--skip-apt`: Skip package installation when dependencies are already present.
- `--enable-remote-cups`: Enables remote IPP access and printer sharing (`cupsctl --share-printers --remote-any`).
- `--enable-cups-admin`: Enables remote CUPS admin UI (`/admin`) and implies `--enable-remote-cups`.

## Print Test

```bash
lp -d thermal /path/to/your-label.pdf
```

## macOS / iPhone Setup

### macOS (IPP)

Use IPP and the shared CUPS queue:

- URI: `ipp://thermalmini.local:631/printers/thermal`
- Fallback URI: `ipp://<pi-ip>:631/printers/thermal`

Terminal setup on macOS:

```bash
sudo lpadmin -p thermalmini -E \
  -v ipp://thermalmini.local:631/printers/thermal \
  -m everywhere
sudo lpoptions -d thermalmini
```

If `-m everywhere` fails, use the Generic PostScript PPD as a fallback.

### iPhone / iPad (AirPrint)

When CUPS sharing and Bonjour (`dnssd`) are enabled, the queue may appear as an AirPrint printer in iOS. If discovery is unreliable, macOS manual IPP setup will still work using the URI above.

## Operational Notes

- Installer now adds a stable printer symlink rule (`/dev/thermal-printer`) via udev (best for a single USB printer on the Pi).
- The server probes device paths in this order: `THERMAL_DEVICE_PATH`, `/dev/thermal-printer`, `/dev/usb/lp0`, `/dev/usb/lp1`, ...
- `/healthz` returns service + hardware status (`printer_connected`, resolved device path, current image-processing settings).
- Installer alignment (`GAPDETECT` + `HOME`) is non-fatal and will be skipped with a warning if no printer device is connected.

## Full-Bleed / Sticker Printing

- Top whitespace auto-trimming is now disabled by default to preserve exact page canvas/bleed edges for full-page stickers.
- The server no longer crops image height when trim is enabled; it shifts content up while preserving the canvas size.
- If you want the old behavior (auto top-trim compensation), set:

```bash
sudo sh -c 'printf "%s\n" "THERMAL_AUTO_TRIM_TOP_WHITESPACE=1" > /etc/default/thermal-printer'
sudo systemctl restart thermal-printer.service
```

- Additional alignment tuning (if needed) can be set in `/etc/default/thermal-printer`:
  - `THERMAL_X_OFFSET`
  - `THERMAL_Y_OFFSET`
  - `THERMAL_HORIZONTAL_SHIFT_PX`
  - `THERMAL_AUTO_TRIM_TOP_WHITESPACE`

## Notes

- Installer writes backups as `*.bak.YYYYMMDD-HHMMSS` before replacing files.
- Installer attempts `GAPDETECT` + `HOME` after setup to align gap-mark media (warning-only if printer is unplugged).
- Current calibration lives in `files/opt/thermal-printer/print_server.py`:
  - `Y_OFFSET`
  - `MAX_TOP_TRIM_PX`
  - `HORIZONTAL_SHIFT_PX`
- Snapshot file hashes are in `SNAPSHOT_SHA256SUMS.txt`.
