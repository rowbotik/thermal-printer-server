#!/usr/bin/env python3
"""
Image to TSPL Bitmap Converter for ORGSTA T001
Converts images to TSPL BITMAP commands
"""

from PIL import Image
import sys

def image_to_tspl(image_path, x=0, y=0, dither=True):
    """
    Convert image to TSPL BITMAP command
    
    Args:
        image_path: Path to image file
        x, y: Position on label (in dots, 203 DPI)
        dither: Use Floyd-Steinberg dithering for grayscale
    
    Returns:
        TSPL command string
    """
    # Open and convert to grayscale
    img = Image.open(image_path).convert('L')
    
    # Resize to fit 4x6 label at 203 DPI
    # Max size: 812 x 1218 pixels
    img.thumbnail((812, 1218), Image.Resampling.LANCZOS)
    
    width, height = img.size
    
    # Apply dithering if requested (better for photos/logos)
    if dither:
        img = img.convert('1', dither=Image.Dither.FLOYDSTEINBERG)
    else:
        img = img.point(lambda x: 0 if x < 128 else 255, '1')
    
    # Convert to bytes
    # TSPL BITMAP format: each byte = 8 horizontal pixels
    # LSB first (bit 0 = leftmost pixel in byte)
    pixels = list(img.getdata())
    
    # Ensure width is multiple of 8
    padded_width = (width + 7) // 8 * 8
    
    bitmap_bytes = []
    for row in range(height):
        row_start = row * width
        for byte_col in range(0, padded_width, 8):
            byte_val = 0
            for bit in range(8):
                pixel_col = byte_col + bit
                if pixel_col < width:
                    # 0 = black (print), 255 = white (no print)
                    # TSPL: 1 = print (black), 0 = no print
                    pixel_val = pixels[row_start + pixel_col]
                    if pixel_val < 128:  # Black
                        byte_val |= (1 << (7 - bit))  # MSB first
            bitmap_bytes.append(byte_val)
    
    # Convert to hex string
    hex_data = ''.join(f'{b:02X}' for b in bitmap_bytes)
    
    # TSPL command
    # BITMAP x,y,width_bytes,height,mode,data
    # mode: 0 = OR, 1 = AND, 2 = XOR (usually 0)
    width_bytes = padded_width // 8
    
    # Split hex data into chunks (TSPL has line length limits)
    chunk_size = 4000  # Safe chunk size
    hex_chunks = [hex_data[i:i+chunk_size] for i in range(0, len(hex_data), chunk_size)]
    
    tspl_lines = [
        f"BITMAP {x},{y},{width_bytes},{height},0,"
    ]
    tspl_lines.extend(hex_chunks)
    
    return '\n'.join(tspl_lines), width, height

def create_text_bitmap(text, font_size=40, x=0, y=0):
    """Create a bitmap from text using PIL"""
    from PIL import ImageDraw, ImageFont
    
    # Create image with text
    img = Image.new('L', (812, 200), 255)  # White background
    draw = ImageDraw.Draw(img)
    
    # Try to load a font, fall back to default
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", font_size)
    except:
        font = ImageFont.load_default()
    
    draw.text((10, 10), text, fill=0, font=font)  # Black text
    
    # Crop to content
    bbox = img.getbbox()
    if bbox:
        img = img.crop(bbox)
    
    # Save temporarily and convert
    temp_path = "/tmp/text_bitmap.png"
    img.save(temp_path)
    
    return image_to_tspl(temp_path, x, y, dither=False)

# Example usage
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python image_to_tspl.py <image.png> [x] [y]")
        print("   or: python image_to_tspl.py --text 'Your Text' [size]")
        sys.exit(1)
    
    if sys.argv[1] == '--text':
        text = sys.argv[2]
        size = int(sys.argv[3]) if len(sys.argv) > 3 else 40
        tspl, w, h = create_text_bitmap(text, size)
        print(f"Text: '{text}'")
        print(f"Size: {w}x{h} pixels")
        print("\nTSPL Commands:")
        print(tspl)
    else:
        image_path = sys.argv[1]
        x = int(sys.argv[2]) if len(sys.argv) > 2 else 0
        y = int(sys.argv[3]) if len(sys.argv) > 3 else 0
        
        tspl, w, h = image_to_tspl(image_path, x, y)
        print(f"Image: {image_path}")
        print(f"Converted to: {w}x{h} pixels ({w//8} bytes wide)")
        print(f"\nTSPL Commands (save to file or send directly):")
        print(tspl)
