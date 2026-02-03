# Adobe Illustrator Label Design Guide
## ORGSTA T001 4x6 Thermal Printer

---

## Document Setup

### New Document Settings
| Setting | Value |
|---------|-------|
| **Width** | 4 inches |
| **Height** | 6 inches |
| **Units** | Inches (or Points: 288 x 432 pt) |
| **Color Mode** | Grayscale |
| **Raster Effects** | 203 ppi |

### OR Open the Template
Open `ORGSTA_T001_Template.eps` in Illustrator - it's pre-configured with:
- Correct 4x6 artboard
- Safe area guides (0.125" margin)
- Section guides for logo/content/barcode areas
- Resolution notes

---

## Design Rules

### 1. Color (CRITICAL)
- **Use ONLY black and white**
- NO grayscale, NO colors, NO gradients
- Black = prints (heated)
- White = no print (paper stays white)

### 2. Resolution
- Design at **203 DPI** equivalent
- Export final image at **812 x 1218 pixels**
- Minimum line weight: 1 pixel (0.005")

### 3. Bleed & Margins
- **Full bleed**: Design can go to edge (0,0 to 4,6)
- **Safe area**: Keep critical text 0.125" from edges
- The template shows safe zone with dashed line

### 4. Text
- **Font size**: Minimum 8pt for readability
- **Bold weights** work better than thin
- Sans-serif fonts recommended (Helvetica, Arial, etc.)
- Convert text to outlines before export

---

## Export Settings

### Method 1: Export as PNG (Recommended)
1. File → Export → Export As
2. Format: PNG
3. Click "Use Artboards"
4. Export settings:
   - **Resolution**: Other → 203 ppi
   - **Background**: White
   - **Anti-aliasing**: None (or Art Optimized)

### Method 2: Export as BMP
1. File → Export → Export As
2. Format: BMP
3. Resolution: 203 ppi
4. Color Model: Grayscale
5. Depth: 1-bit (if available)

---

## Conversion to TSPL (Printable Format)

After exporting from Illustrator, convert to TSPL commands:

### On the Pi:
```bash
# Upload your exported PNG/BMP to the Pi
scp your_label.png alex@thermal.local:/tmp/

# Convert and print
ssh alex@thermal.local
python3 /home/alex/image_to_tspl.py /tmp/your_label.png 0 0 > /tmp/label.tspl
cat /tmp/label.tspl | sudo tee /dev/usb/lp0
```

### Or via HTTP API (I can add an endpoint):
```bash
# Upload image and print
curl -X POST http://thermal.local:8765/image \
  -F "image=@your_label.png" \
  -F "x=0" \
  -F "y=0"
```

---

## Design Layout Ideas

### Full-Bleed Background + Text Overlay
1. Create full 4x6 background pattern in Illustrator
2. Export as bitmap
3. Layer text on top with TSPL TEXT commands

### Section-Based Design
```
+------------------+
|    LOGO (1")     |  <- BITMAP or TEXT
+------------------+
|                  |
|   CONTENT (3.5") |  <- TEXT, BOXES, LINES
|                  |
+------------------+
|  BARCODE (1.5")  |  <- TSPL BARCODE command
+------------------+
```

---

## Testing Your Design

1. **Design in Illustrator** using template
2. **Export as PNG** at 203 ppi, 812x1218px
3. **Test print** using conversion script
4. **Adjust** and repeat

---

## Example Workflow

```bash
# 1. Design in Illustrator, save as my_label.ai
# 2. Export as my_label.png (203 ppi, 812x1218)
# 3. Convert and print:
python3 image_to_tspl.py my_label.png > label.tspl
cat label.tspl | sudo tee /dev/usb/lp0

# Or combine with text overlay:
cat > /tmp/full_label.tspl << 'EOF'
SIZE 4,6
CLS
BITMAP 0,0,101,1218,0,[your image hex]
TEXT 50,50,"3",0,1,1,"ORDER #12345"
PRINT 1
EOF
```

---

## Common Issues

| Problem | Solution |
|---------|----------|
| Image too fuzzy | Export at exactly 203 ppi, not higher |
| Lines not printing | Minimum 1px width, convert strokes to outlines |
| Text missing | Convert to outlines, or use TSPL TEXT command |
| Wrong colors | Ensure pure black (#000000) and white (#FFFFFF) only |
| File too large | TSPL has limits; split into multiple BITMAP commands |

---

## Template Files

- `ORGSTA_T001_Template.eps` - Open in Illustrator
- `image_to_tspl.py` - Python converter script
- `label_examples/` - Sample layouts

## Need Help?

Send me your Illustrator file and I'll:
1. Check it meets specs
2. Convert to TSPL
3. Test print and send photo
