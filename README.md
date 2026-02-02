# Thermal Printer Server for ORGSTA T001

HTTP API server for ORGSTA T001 thermal label printer. Converts images to TSPL2 format and provides label templates.

## Features

- ✅ Text-based labels (packing lists, shipping labels)
- ✅ Barcode printing (Code 128)
- ✅ Image printing with automatic dithering
- ✅ HTTP REST API
- ✅ Works on Raspberry Pi (Zero, 3, 4, 5)
- ✅ No vendor drivers required (pure Python)

## Hardware Requirements

- ORGSTA T001 or compatible TSPL2 printer
- Raspberry Pi (any model) or Linux computer
- USB connection (printer must be on powered hub for Pi Zero)
- Network connection (WiFi or Ethernet)

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

### POST /raw
Send raw TSPL commands
```bash
curl -X POST http://thermal.local:8765/raw -d "
SIZE 4,6
CLS
TEXT 50,50,\"3\",0,1,1,\"Hello World\"
PRINT 1,1
"
```

## Key Discovery: TSPL BITMAP Format

### The Problem

ORGSTA provides Linux drivers as x86_64 AppImages that don't work on ARM (Raspberry Pi). The PPD file references a proprietary filter:
```
*cupsFilter: "application/vnd.cups-raster 0 rastertosnailtspl-orgsta"
```

This filter converts CUPS raster data to TSPL2 bitmap format. Without it, direct image printing fails.

### The Solution

Reverse-engineered the TSPL BITMAP format from ORGSTA's Chrome OS driver (a Chrome extension that's pure JavaScript and architecture-independent).

### TSPL BITMAP Format

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
5. No line breaks between header and data

**Example (Python):**
```python
# 16x8 black square
# width_bytes = 16/8 = 2
# Each row: 2 bytes = 16 bits
header = "BITMAP 0,0,2,8,0,"  # Note the trailing comma
data = bytes([0xFF, 0xFF]) * 8  # 8 rows of all-black

with open('/dev/usb/lp0', 'wb') as f:
    f.write(header.encode())
    f.write(data)
```

### Chrome OS Driver Analysis

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
The TSPL BITMAP format is very specific. If using custom code, ensure:
- Width is multiple of 8
- Sending raw bytes, not hex strings
- MSB first bit order
- Header ends with comma, no newline before data

## Files

- `print_server.py` - Main HTTP server
- `install.sh` - Installation script
- `install-on-boot.sh` - Pull latest from GitHub on boot (optional)
- `README.md` - This file

## License

MIT - Use at your own risk for thermal printing adventures.

## Credits

- Reverse engineering: Analyzed ORGSTA Chrome OS driver
- Format discovery: Chrome OS extension JavaScript
- Implementation: Pure Python + Pillow
- No proprietary binaries required
