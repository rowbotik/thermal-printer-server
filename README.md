# Thermal Printer Server for ORGSTA T001

HTTP API server for ORGSTA T001 thermal label printer. Converts images to TSPL2 format and provides label templates.

## Features

- ✅ Text-based labels (packing lists, shipping labels)
- ✅ Barcode printing (Code 128)
- ✅ Image printing with automatic dithering
- ✅ HTTP REST API
- ✅ Works on Raspberry Pi (Zero, 3, 4, 5)
- ✅ No vendor drivers required (pure Python)
- ✅ Perforated roll label support (gap detection disabled)

## Hardware Requirements

- ORGSTA T001 or compatible TSPL2 printer
- Raspberry Pi (any model) or Linux computer
- USB connection (printer must be on powered hub for Pi Zero)
- Network connection (WiFi or Ethernet)
- **Labels:** 4" x 159mm (101.6mm x 159mm) continuous roll with perforations

## Quick Start

### 1. Install

```bash
# Clone or copy this directory to your Pi
cd thermal-printer-server
sudo ./install.sh
```

### 2. Test

```bash
# Check server is running
curl http://localhost:8765/

# Print test label
curl -X POST http://localhost:8765/print -d "Line 1
Line 2
Line 3"
```

## API Endpoints

### POST /print
Simple text label
```bash
curl -X POST http://thermal.local:8765/print -d "Line 1
Line 2
Line 3"
```

### POST /shipping
Shipping label with barcode
```bash
curl -X POST http://thermal.local:8765/shipping \
  -d "54321|Jane Doe|123 Oak Ave, Detroit|ORDER54321"
```

### POST /packing
Packing list
```bash
curl -X POST http://thermal.local:8765/packing \
  -d "99999|John Smith|Widget A,Widget B,Widget C"
```

### POST /image
Print image (base64 encoded PNG/JPG)
```bash
curl -X POST http://thermal.local:8765/image \
  -d "$(base64 -i logo.png)"
```

**Important:** Images should be sized to 812x1218 pixels (4x6 at 203 DPI). The printer inverts colors (black→white, white→black).

### POST /raw
Send raw TSPL commands
```bash
curl -X POST http://thermal.local:8765/raw -d "
SIZE 101.6mm,159mm
GAP 0,0
CLS
TEXT 50,50,\"3\",0,1,1,\"Hello World\"
PRINT 1,1
"
```

## Key Discoveries

### 1. TSPL BITMAP Format (from Chrome OS Driver)

ORGSTA's Linux drivers are x86_64 only. Reverse-engineered the TSPL BITMAP format from their Chrome OS extension:

```
BITMAP x,y,width_bytes,height,mode,raw_binary_data
```

- **x, y**: Position in dots (203 DPI)
- **width_bytes**: Width in bytes (width_pixels / 8, rounded up)
- **height**: Height in pixels
- **mode**: 0 (OR mode)
- **raw_binary_data**: Raw bytes, not hex encoded

**Critical requirements:**
1. Width must be byte-aligned (multiple of 8 pixels)
2. MSB first: bit 7 = leftmost pixel in byte
3. 1 = print (black), 0 = no print (white)
4. Send header as ASCII ending with comma, then raw bytes immediately
5. **Padding pixels must be 0 (white)** - not left as garbage
6. **Image must be inverted** before processing (printer expects negative)

### 2. Perforated Roll Labels

Roll labels with perforation holes trigger the printer's gap sensor, causing misalignment.

**Solution:** Disable gap detection:
```
GAP 0,0
```

This tells the printer to use continuous feed mode instead of looking for gaps between labels.

### 3. Label Size Configuration

Default: **4" x 159mm** (101.6mm x 159mm)

Edit in `print_server.py`:
```python
LABEL_WIDTH_MM = 101.6   # 4 inches
LABEL_HEIGHT_MM = 159    # Roll height
```

### 4. Image Positioning

The printer has an unprintable top margin. Use Y_OFFSET to push content down:
```python
Y_OFFSET = 20   # 20 dots ≈ 2.5mm from top
```

## Mac Printing

Resize image to proper label dimensions, then send:

```bash
# Resize template to 812x1218 (4x6 at 203 DPI)
sips -z 1218 812 ~/Sync/My_ORGSTA_T001_Template.png --out /tmp/label.png

# Send to printer
curl -X POST http://thermal.local:8765/image -d "$(base64 -i /tmp/label.png)"
```

Or create a simple script:
```bash
#!/bin/bash
# Save as /usr/local/bin/print-label
INPUT="$1"
TEMP="/tmp/label_$$.png"
sips -z 1218 812 "$INPUT" --out "$TEMP"
curl -X POST http://thermal.local:8765/image -d "$(base64 -i "$TEMP")"
rm "$TEMP"
```

## Chrome OS Driver Analysis

Downloaded from: https://orgsta.com/wp-content/uploads/2025/10/Chrome-OS.zip

Key findings from `static/background/index.js`:

```javascript
composePrintImage=(e,t=i.HalftoneType.Disabled)=>{
  let u=(0,o.numberAlign)(e.width,8),  // Align width to 8 pixels
  r=new s(u,e.height),
  n=`BITMAP 0,0,${u/8},${e.height},0,`,  // Header with trailing comma
  // ... MSB-first bit packing
```

This confirmed the exact format needed for working image printing.

## Troubleshooting

### Printer not found
Check device path:
```bash
ls -la /dev/usb/lp*
```

Update path in `print_server.py` if different.

### Permission denied
Ensure user is in `lp` group:
```bash
sudo usermod -a -G lp pi
```

### Service won't start
Check logs:
```bash
sudo journalctl -u thermal-printer -f
```

### Images print as stripes/garbage
The TSPL BITMAP format is very specific. Ensure:
- Width is multiple of 8
- Sending raw bytes, not hex strings
- MSB first bit order
- Header ends with comma, no newline before data
- Padding pixels are 0 (white)

### Label feeds to wrong position / stops mid-print
Your labels likely have perforations that trigger the gap sensor.

**Fix:** The server uses `GAP 0,0` which disables gap detection. If printing raw TSPL, add this before printing:
```
GAP 0,0
```

### Black line on right side of image
Padding bytes were not set to white. Fixed in current version - extra pixels are always set to 0.

### Image colors inverted (black↔white)
The printer expects inverted images. The server handles this automatically - if printing raw, invert your image first:
```python
img = Image.eval(img, lambda x: 255 - x)
```

### Top margin too large / content cut off
The printer has a physical unprintable area at the top. The server uses `Y_OFFSET = 20` to push content down. Adjust if needed.

## Files

- `print_server.py` - Main HTTP server with all fixes
- `install.sh` - Installation script
- `install-on-boot.sh` - Pull latest from GitHub on boot (optional)
- `README.md` - This file

## Configuration

Edit these values in `print_server.py` for your setup:

```python
# Label dimensions (mm)
LABEL_WIDTH_MM = 101.6   # 4 inches
LABEL_HEIGHT_MM = 159    # Adjust to your roll

# Print positioning
X_OFFSET = 0             # Adjust for left margin
Y_OFFSET = 20            # Adjust for top margin

# Printer device
DEVICE = '/dev/usb/lp0'  # Update if different
```

## Pi Zero Notes

The Pi Zero works great with this setup because:
- Pure Python implementation (no x86_64 binaries needed)
- Low resource usage
- Powered USB hub handles printer power

Install is identical to Pi 4.

## License

MIT - Use at your own risk for thermal printing adventures.

## Credits

- Reverse engineering: Analyzed ORGSTA Chrome OS driver
- Format discovery: Chrome OS extension JavaScript
- Implementation: Pure Python + Pillow
- No proprietary binaries required
- Tested on 4" x 159mm perforated roll labels
