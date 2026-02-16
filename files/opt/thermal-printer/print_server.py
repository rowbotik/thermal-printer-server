#!/usr/bin/env python3
"""
Thermal Printer Server for ORGSTA T001
Fixed version with proper gap detection and roll label support
"""

import http.server
import socketserver
import json
import base64
import io
import sys
from datetime import datetime
from PIL import Image

PORT = 8765

# Label configuration for 4" x 6" labels
LABEL_WIDTH_MM = 101.6  # 4 inches
LABEL_HEIGHT_MM = 152.4   # Roll height
X_OFFSET = 0            # Adjust if left margin too big
Y_OFFSET = 0           # Adjust for top margin
AUTO_TRIM_TOP_WHITESPACE = True
WHITE_THRESHOLD = 245
MAX_TOP_TRIM_PX = 80
HORIZONTAL_SHIFT_PX = -20  # Negative shifts left, positive shifts right

def trim_top_whitespace(img):
    """Trim blank rows above content to reduce leading white space."""
    if not AUTO_TRIM_TOP_WHITESPACE:
        return img

    mask = img.point(lambda p: 255 if p < WHITE_THRESHOLD else 0, '1')
    bbox = mask.getbbox()
    if not bbox:
        return img

    top = bbox[1]
    if top <= 0:
        return img

    trim_px = min(top, MAX_TOP_TRIM_PX)
    width, height = img.size
    return img.crop((0, trim_px, width, height))

def shift_image_horizontally(img, shift_px):
    """Shift image content left/right while keeping canvas size constant."""
    if shift_px == 0:
        return img

    width, height = img.size
    if abs(shift_px) >= width:
        return Image.new('L', (width, height), 255)

    shifted = Image.new('L', (width, height), 255)
    if shift_px > 0:
        source = img.crop((0, 0, width - shift_px, height))
        shifted.paste(source, (shift_px, 0))
    else:
        shift_left = -shift_px
        source = img.crop((shift_left, 0, width, height))
        shifted.paste(source, (0, 0))

    return shifted

def image_to_tspl(image_data, x=X_OFFSET, y=Y_OFFSET, dither=True):
    """
    Convert image to TSPL BITMAP command with raw binary data
    Fixed: proper padding, inverted colors, gap disabled for perforated labels
    """
    img = Image.open(io.BytesIO(image_data)).convert('L')
    
    img = trim_top_whitespace(img)
    img = shift_image_horizontally(img, HORIZONTAL_SHIFT_PX)

    # Keep original size, don't resize
    width, height = img.size
    
    # Invert image (printer expects inverted)
    img = Image.eval(img, lambda x: 255 - x)
    
    # Apply dithering
    if dither:
        img = img.convert('1', dither=Image.Dither.FLOYDSTEINBERG)
    else:
        img = img.point(lambda x: 0 if x < 128 else 255, '1')
    
    # Calculate proper byte width (TSPL requires byte alignment)
    width_bytes = (width + 7) // 8
    padded_width = width_bytes * 8
    
    pixels = list(img.getdata())
    
    # Build bitmap bytes - MSB first, padding pixels are white (0)
    bitmap_bytes = bytearray()
    
    for row in range(height):
        row_start = row * width
        for byte_col in range(0, padded_width, 8):
            byte_val = 0
            for bit in range(8):
                pixel_col = byte_col + bit
                if pixel_col < width:  # Real pixel
                    pixel_val = pixels[row_start + pixel_col]
                    if pixel_val < 128:  # Black
                        byte_val |= (1 << (7 - bit))
                # Padding pixels stay 0 (white)
            bitmap_bytes.append(byte_val)
    
    header = f"BITMAP {x},{y},{width_bytes},{height},0,"
    
    return header, bytes(bitmap_bytes)

class LabelTemplates:
    @staticmethod
    def standard_shipping(order, customer, address, barcode=None, date_str=None):
        """Standard shipping label"""
        if date_str is None:
            date_str = datetime.now().strftime('%Y-%m-%d')
        
        tspl = [
            f"SIZE {LABEL_WIDTH_MM}mm,{LABEL_HEIGHT_MM}mm",
            "GAP 3mm,0mm",  # Enable gap sensing for label media
            "CLS",
            "BOX 40,20,400,100,4",
            'TEXT 50,35,"3",0,1,1,"ATK FABRICATION CO."',
            'TEXT 50,75,"1",0,1,1,"Quality Fabrication & Design"',
            "BAR 40,110,360,3",
            f'TEXT 50,130,"2",0,1,1,"Order: #{order}"',
            f'TEXT 50,180,"2",0,1,1,"Date: {date_str}"',
            "BAR 40,230,360,2",
            'TEXT 50,250,"2",0,1,1,"SHIP TO:"',
            'TEXT 70,300,"2",0,1,1,""',
        ]
        
        addr_lines = address.split(',') if ',' in address else [address[i:i+30] for i in range(0, min(len(address), 90), 30)]
        y = 330
        for line in addr_lines[:3]:
            safe_line = line.strip().replace('"', '\\"')[:35]
            tspl.append(f'TEXT 70,{y},"2",0,1,1,"{safe_line}"')
            y += 50
        
        bc = barcode if barcode else order
        tspl.extend([
            "BAR 40,500,360,2",
            f'BARCODE 80,520,"128",80,1,0,2,2,"{bc[:25]}"',
            f'TEXT 80,620,"1",0,1,1,"{bc[:25]}"',
        ])
        
        tspl.append("PRINT 1,1")
        return "\n".join(tspl)
    
    @staticmethod
    def simple_text(lines, title="ATK FABRICATION"):
        """Simple text-only label"""
        tspl = [
            f"SIZE {LABEL_WIDTH_MM}mm,{LABEL_HEIGHT_MM}mm",
            "GAP 3mm,0mm",
            "CLS",
            f'TEXT 50,30,"3",0,1,1,"{title}"',
            "BAR 50,80,400,4",
        ]
        y = 110
        for line in lines[:8]:
            safe = line.replace('"', '\\"')[:40]
            tspl.append(f'TEXT 50,{y},"2",0,1,1,"{safe}"')
            y += 55
        tspl.append("PRINT 1,1")
        return "\n".join(tspl)
    
    @staticmethod
    def packing_list(order, items, customer):
        """Internal packing list"""
        tspl = [
            f"SIZE {LABEL_WIDTH_MM}mm,{LABEL_HEIGHT_MM}mm",
            "GAP 3mm,0mm",
            "CLS",
            'TEXT 50,30,"3",0,1,1,"PACKING LIST"',
            f'TEXT 50,90,"2",0,1,1,"Order: #{order}"',
            f'TEXT 50,140,"2",0,1,1,"Customer: {customer[:30]}"',
            "BAR 50,190,400,3",
            'TEXT 50,210,"2",0,1,1,"ITEMS:"',
        ]
        y = 260
        for i, item in enumerate(items[:6], 1):
            safe = item.replace('"', '\\"')[:35]
            tspl.append(f'TEXT 70,{y},"2",0,1,1,"{i}. {safe}"')
            y += 50
        tspl.append("PRINT 1,1")
        return "\n".join(tspl)

def send_tspl(tspl_data):
    """Write TSPL data to printer"""
    with open('/dev/usb/lp0', 'wb') as f:
        f.write((tspl_data + "\n").encode())
    return True

def send_tspl_bytes(tspl_bytes):
    """Write raw TSPL bytes to printer"""
    with open('/dev/usb/lp0', 'wb') as f:
        f.write(tspl_bytes)
    return True

class Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass
    
    def send_json(self, data, code=200):
        self.send_response(code)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())
    
    def do_POST(self):
        content_len = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_len)
        
        try:
            if self.path == '/print':
                lines = body.decode('utf-8').strip().split('\n')
                tspl = LabelTemplates.simple_text(lines)
                send_tspl(tspl)
                self.send_json({"status": "printed", "lines": len(lines), "template": "simple"})
            
            elif self.path == '/shipping':
                parts = body.decode('utf-8').strip().split('|')
                if len(parts) >= 3:
                    order, customer, address = parts[0], parts[1], parts[2]
                    barcode = parts[3] if len(parts) > 3 else order
                    tspl = LabelTemplates.standard_shipping(order, customer, address, barcode)
                    send_tspl(tspl)
                    self.send_json({"status": "printed", "order": order, "template": "shipping"})
                else:
                    self.send_json({"error": "Format: order|customer|address|barcode"}, 400)
            
            elif self.path == '/packing':
                parts = body.decode('utf-8').strip().split('|')
                if len(parts) >= 3:
                    order, customer = parts[0], parts[1]
                    items = parts[2].split(',')
                    tspl = LabelTemplates.packing_list(order, items, customer)
                    send_tspl(tspl)
                    self.send_json({"status": "printed", "order": order, "template": "packing", "items": len(items)})
                else:
                    self.send_json({"error": "Format: order|customer|item1,item2,item3"}, 400)
            
            elif self.path == '/raw':
                send_tspl(body.decode('utf-8'))
                self.send_json({"status": "printed", "mode": "raw"})
            
            elif self.path == '/image':
                try:
                    image_data = base64.b64decode(body)
                    header, bitmap_data = image_to_tspl(image_data)
                    
                    output = bytearray()
                    output.extend(f"SIZE {LABEL_WIDTH_MM}mm,{LABEL_HEIGHT_MM}mm\n".encode())
                    output.extend(b"GAP 3mm,0mm\n")  # Enable gap sensing for label media
                    output.extend(b"CLS\n")
                    output.extend(header.encode('ascii'))
                    output.extend(bitmap_data)
                    output.extend(b"\nPRINT 1,1\n")
                    
                    send_tspl_bytes(output)
                    self.send_json({"status": "printed", "template": "image"})
                except Exception as e:
                    self.send_json({"error": f"Image processing failed: {str(e)}"}, 500)
            
            else:
                self.send_error(404)
        
        except Exception as e:
            self.send_json({"error": str(e)}, 500)
    
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        help_text = f"""Thermal Label Printer API - ATK Fabrication

LABEL SIZE: {LABEL_WIDTH_MM}mm x {LABEL_HEIGHT_MM}mm (4" x 6")
GAP DETECTION: Enabled (3mm) for label media

ENDPOINTS:
POST /print      - Simple text (body: "Line 1\nLine 2")
POST /shipping   - Shipping label (body: "order|customer|address|barcode")  
POST /packing    - Packing list (body: "order|customer|item1,item2,item3")
POST /raw        - Raw TSPL commands
POST /image      - Base64-encoded PNG/JPG image

EXAMPLES:
curl -X POST http://thermal.local:8765/shipping -d "54321|Jane Doe|123 Oak Ave, Detroit|ORDER54321"

curl -X POST http://thermal.local:8765/packing -d "99999|John Smith|Widget A,Widget B,Widget C"

# Print image (base64 encoded)
curl -X POST http://thermal.local:8765/image -d "$(base64 -i logo.png)"
"""
        self.wfile.write(help_text.encode())

if __name__ == '__main__':
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("0.0.0.0", PORT), Handler) as httpd:
        print(f"Label printer server on port {PORT}")
        print(f"Label size: {LABEL_WIDTH_MM}mm x {LABEL_HEIGHT_MM}mm")
        httpd.serve_forever()
