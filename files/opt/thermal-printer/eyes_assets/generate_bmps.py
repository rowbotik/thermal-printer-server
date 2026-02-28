#!/usr/bin/env python3
"""
Generate pixelated eye BMPs for eInk display (250x122, 1-bit)
Pure Python - no PIL required
"""

import os
import struct

ASSET_DIR = "eyes_assets"
WIDTH, HEIGHT = 250, 122

# Pixel art templates (X = black, space = white)
TEMPLATES = {
    'sleep': [
        "                        ",
        "                        ",
        "      XXXXXXXX          XXXXXXXX      ",
        "                        ",
        "                        ",
        "                        ",
        "      XXXXXXXX          XXXXXXXX      ",
        "                        ",
        "                        ",
    ],
    'one_eye': [
        "                        ",
        "                        ",
        "      XXXXXXXX          XXXXXXXX      ",
        "     XXXXXXXXXX        X        X     ",
        "    XXXX XX XXXX      X         X    ",
        "     XXXXXXXXXX        X        X     ",
        "      XXXXXXXX          XXXXXXXX      ",
        "                        ",
        "                        ",
    ],
    'awake': [
        "                        ",
        "                        ",
        "      XXXXXXXX          XXXXXXXX      ",
        "     XXXXXXXXXX        XXXXXXXXXX     ",
        "    XXXX XX XXXX      XXXX XX XXXX    ",
        "     XXXXXXXXXX        XXXXXXXXXX     ",
        "      XXXXXXXX          XXXXXXXX      ",
        "                        ",
        "                        ",
    ],
    'blink': [
        "                        ",
        "                        ",
        "      XXXXXXXX          XXXXXXXX      ",
        "                        ",
        "                        ",
        "                        ",
        "      XXXXXXXX          XXXXXXXX      ",
        "                        ",
        "                        ",
    ],
    'look_left': [
        "                        ",
        "                        ",
        "    XXXXXXXX            XXXXXXXX      ",
        "   XXXXXXXXXX          XXXXXXXXXX     ",
        "  XX XX XXXXX         XX XX XXXXX     ",
        "   XXXXXXXXXX          XXXXXXXXXX     ",
        "    XXXXXXXX            XXXXXXXX      ",
        "                        ",
        "                        ",
    ],
    'look_right': [
        "                        ",
        "                        ",
        "      XXXXXXXX            XXXXXXXX    ",
        "     XXXXXXXXXX          XXXXXXXXXX   ",
        "     XXXXX XX XX         XXXXX XX XX  ",
        "     XXXXXXXXXX          XXXXXXXXXX   ",
        "      XXXXXXXX            XXXXXXXX    ",
        "                        ",
        "                        ",
    ],
    'look_up': [
        "                        ",
        "     XX          XX     ",
        "    XXXX        XXXX    ",
        "   XXXXXX      XXXXXX   ",
        "   XXXXXX      XXXXXX   ",
        "   XX  XX      XX  XX   ",
        "    XXXX        XXXX    ",
        "                        ",
        "                        ",
    ],
    'look_down': [
        "                        ",
        "                        ",
        "    XXXX        XXXX    ",
        "   XX  XX      XX  XX   ",
        "   XXXXXX      XXXXXX   ",
        "   XXXXXX      XXXXXX   ",
        "    XXXX        XXXX    ",
        "     XX          XX     ",
        "                        ",
    ],
    'suspicious': [
        "                        ",
        "                        ",
        "      XXXXXXXX          XXXXXXXX      ",
        "     XXXXXXXXXX        XXXXXXXXXX     ",
        "    XXXXXXXXXXX        XXXXXX XXXX    ",
        "     XXXXXXXXXX        XXXXXXXXXX     ",
        "      XXXXXXXX          XXXXXXXX      ",
        "                        ",
        "                        ",
    ],
    'surprised': [
        "                        ",
        "                        ",
        "      XXXXXXXX          XXXXXXXX      ",
        "     XXXXXXXXXX        XXXXXXXXXX     ",
        "    XXXXXXXXXXXX      XXXXXXXXXXXX    ",
        "     XXXXXXXXXX        XXXXXXXXXX     ",
        "      XXXXXXXX          XXXXXXXX      ",
        "                        ",
        "                        ",
    ],
    'wake_0': [
        "                        ",
        "                        ",
        "      XXXXXXXX          XXXXXXXX      ",
        "     XXXXXXXXXX        XXXXXXXXXX     ",
        "                        ",
        "                        ",
        "      XXXXXXXX          XXXXXXXX      ",
        "                        ",
        "                        ",
    ],
    'wake_1': [
        "                        ",
        "                        ",
        "      XXXXXXXX          XXXXXXXX      ",
        "     XXXXXXXXXX        XXXXXXXXXX     ",
        "     XXXXXXXXXX        XXXXXXXXXX     ",
        "     XXXXXXXXXX        XXXXXXXXXX     ",
        "      XXXXXXXX          XXXXXXXX      ",
        "                        ",
        "                        ",
    ],
    'focus': [
        "                        ",
        "                        ",
        "                        ",
        "      XXXXXXXX          XXXXXXXX      ",
        "     XXXX  XXXX        XXXX  XXXX     ",
        "      XXXXXXXX          XXXXXXXX      ",
        "                        ",
        "                        ",
        "                        ",
    ],
}


def template_to_bitmap(template, scale=6):
    """Convert ASCII template to 1-bit bitmap data"""
    lines = [l for l in template if l.strip()]
    h = len(lines)
    w = max(len(l) for l in lines)
    
    # Scale up
    scaled_w = w * scale
    scaled_h = h * scale
    
    # Center on 250x122
    x_off = (WIDTH - scaled_w) // 2
    y_off = (HEIGHT - scaled_h) // 2
    
    # Create pixel data (1-bit, MSB first, padded to 4-byte rows)
    row_bytes = (WIDTH + 7) // 8
    row_padding = (4 - (row_bytes % 4)) % 4
    
    pixels = []
    for y in range(HEIGHT):
        row = []
        for x in range(WIDTH):
            # Map to template coords
            tx = (x - x_off) // scale
            ty = (y - y_off) // scale
            
            # Check bounds and template
            if 0 <= tx < w and 0 <= ty < h and tx < len(lines[ty]):
                pixel = 0 if lines[ty][tx] == 'X' else 1  # 0 = black, 1 = white
            else:
                pixel = 1  # White background
            row.append(pixel)
        
        # Pack bits into bytes (MSB first)
        for byte_start in range(0, WIDTH, 8):
            byte_val = 0
            for bit in range(8):
                if byte_start + bit < WIDTH:
                    byte_val |= (row[byte_start + bit] << (7 - bit))
            pixels.append(byte_val)
        
        # Add row padding
        pixels.extend([0] * row_padding)
    
    return bytes(pixels)


def create_bmp(name, template):
    """Create 1-bit BMP file"""
    # BMP header
    row_bytes = (WIDTH + 7) // 8
    row_padding = (4 - (row_bytes % 4)) % 4
    pixel_data_size = (row_bytes + row_padding) * HEIGHT
    
    # Color table (2 colors: black, white)
    color_table = bytes([
        0, 0, 0, 0,   # Black
        255, 255, 255, 0  # White
    ])
    
    header = struct.pack('<2sIHHI', b'BM', 0, 0, 0, 0)  # Placeholder size
    dib_header = struct.pack('<IiiHHIIiiII', 
        40,           # DIB header size
        WIDTH,        # Width
        HEIGHT,       # Height (positive = bottom-up)
        1,            # Planes
        1,            # Bits per pixel
        0,            # Compression (none)
        pixel_data_size,
        2835,         # X pixels per meter
        2835,         # Y pixels per meter
        2,            # Colors in palette
        0             # Important colors
    )
    
    pixel_offset = 14 + 40 + len(color_table)
    file_size = pixel_offset + pixel_data_size
    
    # Update header with correct size
    header = struct.pack('<2sIHHI', b'BM', file_size, 0, 0, pixel_offset)
    
    # Generate pixel data
    pixel_data = template_to_bitmap(template)
    
    return header + dib_header + color_table + pixel_data


def main():
    os.makedirs(ASSET_DIR, exist_ok=True)
    
    for name, template in TEMPLATES.items():
        path = os.path.join(ASSET_DIR, f'{name}.bmp')
        data = create_bmp(name, template)
        with open(path, 'wb') as f:
            f.write(data)
        print(f'Created: {path} ({len(data)} bytes)')


if __name__ == '__main__':
    main()
