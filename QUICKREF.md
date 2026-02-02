# Quick Reference - Thermal Printer Server

## Installation

```bash
# One-line install from GitHub
curl -sSL https://raw.githubusercontent.com/rowbotik/thermal-printer-server/main/install.sh | sudo bash
```

## Testing

```bash
# Check server
curl http://thermal.local:8765/

# Test text print
curl -X POST http://thermal.local:8765/print -d "Hello
World"

# Test shipping label
curl -X POST http://thermal.local:8765/shipping \
  -d "12345|Alex|123 Main St|ORDER123"

# Test image print (resize first!)
sips -z 1218 812 image.png --out label.png
curl -X POST http://thermal.local:8765/image \
  -d "$(base64 -i label.png)"
```

## Configuration

Edit `/opt/thermal-printer/print_server.py`:

```python
# For different label sizes
LABEL_WIDTH_MM = 101.6   # 4 inches
LABEL_HEIGHT_MM = 159    # Your roll height

# Adjust margins
X_OFFSET = 0             # Left offset (dots)
Y_OFFSET = 20            # Top offset (dots)

# Different printer device
DEVICE = '/dev/usb/lp0'
```

Restart after changes:
```bash
sudo systemctl restart thermal-printer
```

## Common Issues

| Problem | Solution |
|---------|----------|
| Label stops at perforation | Already fixed - uses `GAP 0,0` |
| Black line on right | Fixed - padding set to white |
| Colors inverted | Fixed - auto-inverts images |
| Top margin too big | Adjust `Y_OFFSET` in config |
| Bottom cut off | Check `LABEL_HEIGHT_MM` matches your roll |

## Mac Workflow

```bash
# Create drag-and-drop script
sudo tee /usr/local/bin/print-label << 'EOF'
#!/bin/bash
INPUT="$1"
TEMP="/tmp/label_$$.png"
sips -z 1218 812 "$INPUT" --out "$TEMP"
curl -X POST http://thermal.local:8765/image \
  -d "$(base64 -i "$TEMP")"
rm "$TEMP"
EOF
sudo chmod +x /usr/local/bin/print-label

# Use it
print-label ~/Desktop/label.png
```

## Service Commands

```bash
# Check status
sudo systemctl status thermal-printer

# View logs
sudo journalctl -u thermal-printer -f

# Restart
sudo systemctl restart thermal-printer

# Stop
sudo systemctl stop thermal-printer

# Start on boot
sudo systemctl enable thermal-printer

# Disable on boot
sudo systemctl disable thermal-printer
```

## Label Roll Specs

**Tested with:**
- Size: 4" x 159mm (101.6mm x 159mm)
- Type: Continuous roll with perforations
- Core: 1" or 1.5"
- Printer: ORGSTA T001 (TSPL2)
- DPI: 203

## Pi Zero Setup

Same as Pi 4, but:
- Use powered USB hub
- WiFi instead of ethernet
- Lower power consumption

```bash
# Pi Zero specific: enable USB gadget (optional)
# Allows direct USB connection to Mac without network
```

## Raw TSPL Example

```bash
curl -X POST http://thermal.local:8765/raw -d '
SIZE 101.6mm,159mm
GAP 0,0
CLS
TEXT 50,50,"4",0,1,1,"Hello World"
BOX 50,100,750,1100,8
PRINT 1,1
'
```

## Links

- GitHub: https://github.com/rowbotik/thermal-printer-server
- Chrome OS driver source: https://orgsta.com/wp-content/uploads/2025/10/Chrome-OS.zip
