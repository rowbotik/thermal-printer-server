#!/usr/bin/env python3
"""
Image to TSPL Bitmap Converter for ORGSTA T001
Fixed version based on Chrome OS driver analysis
"""

from PIL import Image
import sys
import io

def image_to_tspl(image_path, x=0, y=0, dither=True):
    """
    Convert image to TSPL BITMAP command with raw binary data
    
    Args:
        image_path: Path to image file
        x, y: Position on label (in dots, 203 DPI)
        dither: Use Floyd-Steinberg dithering for grayscale
    
    Returns:
        (tspl_header, bitmap_bytes) tuple - send header as text, then bytes
    """
    # Open and convert to grayscale
    img = Image.open(image_path).convert('L')
    
    # Resize to fit 4x6 label at 203 DPI
    img.thumbnail((812, 1218), Image.Resampling.LANCZOS)
    
    width, height = img.size
    
    # Apply dithering if requested
    if dither:
        img = img.convert('1', dither=Image.Dither.FLOYDSTEINBERG)
    else:
        img = img.point(lambda x: 0 if x < 128 else 255, '1')
    
    # Ensure width is multiple of 8 (byte alignment required by TSPL)
    padded_width = (width + 7) // 8 * 8
    width_bytes = padded_width // 8
    
    # Get pixel data (0 = black, 255 = white)
    pixels = list(img.getdata())
    
    # Build bitmap bytes
    # TSPL: bit 7 = leftmost pixel (MSB first)
    # 1 = print (black), 0 = no print (white)
    bitmap_bytes = bytearray()
    
    for row in range(height):
        row_start = row * width
        for byte_col in range(0, padded_width, 8):
            byte_val = 0
            for bit in range(8):
                pixel_col = byte_col + bit
                if pixel_col < width:
                    pixel_val = pixels[row_start + pixel_col]
                    if pixel_val < 128:  # Black pixel
                        byte_val |= (1 << (7 - bit))  # MSB first
            bitmap_bytes.append(byte_val)
    
    # TSPL BITMAP command header
    # Format: BITMAP x,y,width_bytes,height,mode,
    # Note: comma at end, raw data follows immediately
    header = f"BITMAP {x},{y},{width_bytes},{height},0,"
    
    return header.encode('ascii'), bytes(bitmap_bytes), width, height

def send_image_to_printer(image_path, device='/dev/usb/lp0', x=0, y=0):
    """
    Send image directly to printer
    """
    header, bitmap_data, width, height = image_to_tspl(image_path, x, y)
    
    # Build complete TSPL command sequence
    tspl = bytearray()
    tspl.extend(b"SIZE 4,6\n")
    tspl.extend(b"CLS\n")
    tspl.extend(header)
    tspl.extend(bitmap_data)
    tspl.extend(b"\nPRINT 1,1\n")
    
    # Write to printer
    with open(device, 'wb') as f:
        f.write(tspl)
    
    return width, height

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python image_to_tspl_fixed.py <image.png> [device]")
        print("Example: python image_to_tspl_fixed.py logo.png /dev/usb/lp0")
        sys.exit(1)
    
    image_path = sys.argv[1]
    device = sys.argv[2] if len(sys.argv) > 2 else '/dev/usb/lp0'
    
    try:
        width, height = send_image_to_printer(image_path, device)
        print(f"✓ Printed: {image_path}")
        print(f"  Size: {width}x{height} pixels")
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
