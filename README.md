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
sudo ./install.sh --user alex --group lp
sudo ./scripts/verify.sh
```

If your user is not `alex`, set `--user <your_user>`.

## Print Test

```bash
lp -d thermal /path/to/your-label.pdf
```

## Notes

- Installer writes backups as `*.bak.YYYYMMDD-HHMMSS` before replacing files.
- Installer runs `GAPDETECT` + `HOME` after setup to align gap-mark media.
- Current calibration lives in `files/opt/thermal-printer/print_server.py`:
  - `Y_OFFSET`
  - `MAX_TOP_TRIM_PX`
  - `HORIZONTAL_SHIFT_PX`
- Snapshot file hashes are in `SNAPSHOT_SHA256SUMS.txt`.
