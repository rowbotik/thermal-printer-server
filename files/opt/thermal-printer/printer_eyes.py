"""
Printer Eyes - eInk display controller for 2.13" V4 (250x122)
Shows sleeping/awake states on thermal printer
"""

import os
import time
import threading
from PIL import Image

# Try to import waveshare eInk library
try:
    import sys
    # Add common waveshare paths
    waveshare_paths = [
        '/home/pi/waveshare/epdlib',
        '/home/pi/e-Paper/RaspberryPi_JetsonNano/python/lib',
        '/usr/local/lib/python3/dist-packages/waveshare_epd',
    ]
    for p in waveshare_paths:
        if os.path.exists(p):
            sys.path.append(p)

    from waveshare_epd import epd2in13_V4
    HAS_EINK = True
except ImportError:
    HAS_EINK = False

# Asset directory
ASSET_DIR = os.path.join(os.path.dirname(__file__), 'eyes_assets')

# Display specs
WIDTH = 250
HEIGHT = 122


class PrinterEyes:
    """Simple eInk eye controller for thermal printer"""

    def __init__(self):
        self.epd = None
        self.current_state = None
        self._lock = threading.Lock()
        self._enabled = HAS_EINK

        if self._enabled:
            try:
                self.epd = epd2in13_V4.EPD()
                self.epd.init()
                self.epd.Clear()
                print("[EYES] eInk display initialized", file=sys.stderr, flush=True)
                self._show_image('sleep')  # Start asleep
            except Exception as e:
                print(f"[EYES] Failed to init display: {e}", file=sys.stderr, flush=True)
                self._enabled = False

    def _get_asset_path(self, name):
        """Get path to BMP asset"""
        path = os.path.join(ASSET_DIR, f'{name}.bmp')
        if os.path.exists(path):
            return path
        # Fallback: generate on the fly
        return self._generate_asset(name)

    def _generate_asset(self, name):
        """Generate a simple eye image if BMP not found"""
        img = Image.new('1', (WIDTH, HEIGHT), 255)  # White background

        if name == 'sleep':
            # Two horizontal lines (closed eyes)
            for y in [45, 77]:
                for x in range(65, 105):
                    img.putpixel((x, y), 0)
                for x in range(145, 185):
                    img.putpixel((x, y), 0)

        elif name == 'wake_0':
            # Eyes 25% open - small ellipses
            self._draw_ellipse(img, 85, 61, 20, 10, 0)  # Left
            self._draw_ellipse(img, 165, 61, 20, 10, 0)  # Right

        elif name == 'wake_1':
            # Eyes 60% open
            self._draw_ellipse(img, 85, 61, 25, 25, 0)
            self._draw_ellipse(img, 165, 61, 25, 25, 0)

        elif name == 'awake':
            # Full open eyes with pupils
            self._draw_ellipse(img, 85, 61, 30, 35, 0)  # Left outline
            self._draw_ellipse(img, 165, 61, 30, 35, 0)  # Right outline
            self._draw_filled_ellipse(img, 85, 61, 12, 12, 0)  # Left pupil
            self._draw_filled_ellipse(img, 165, 61, 12, 12, 0)  # Right pupil
            img.putpixel((89, 57), 255)  # Left highlight
            img.putpixel((169, 57), 255)  # Right highlight

        elif name == 'blink':
            # Closed eyes (same as sleep but quick)
            for y in [45, 77]:
                for x in range(65, 105):
                    img.putpixel((x, y), 0)
                for x in range(145, 185):
                    img.putpixel((x, y), 0)

        elif name == 'focus':
            # Narrowed eyes (concentrating)
            self._draw_ellipse(img, 85, 61, 30, 20, 0)  # Left
            self._draw_ellipse(img, 165, 61, 30, 20, 0)  # Right
            self._draw_filled_ellipse(img, 85, 61, 8, 8, 0)  # Small pupils
            self._draw_filled_ellipse(img, 165, 61, 8, 8, 0)

        # Ensure asset directory exists
        os.makedirs(ASSET_DIR, exist_ok=True)
        path = os.path.join(ASSET_DIR, f'{name}.bmp')
        img.save(path)
        return path

    def _draw_ellipse(self, img, cx, cy, rx, ry, color):
        """Draw ellipse outline on image"""
        import math
        for angle in range(0, 360, 2):
            x = int(cx + rx * math.cos(math.radians(angle)))
            y = int(cy + ry * math.sin(math.radians(angle)))
            if 0 <= x < WIDTH and 0 <= y < HEIGHT:
                img.putpixel((x, y), color)

    def _draw_filled_ellipse(self, img, cx, cy, rx, ry, color):
        """Draw filled ellipse"""
        import math
        for y in range(max(0, cy - ry), min(HEIGHT, cy + ry + 1)):
            for x in range(max(0, cx - rx), min(WIDTH, cx + rx + 1)):
                if ((x - cx) / max(rx, 1)) ** 2 + ((y - cy) / max(ry, 1)) ** 2 <= 1:
                    img.putpixel((x, y), color)

    def _show_image(self, name):
        """Display an image by name"""
        if not self._enabled:
            print(f"[EYES] Would show: {name}", file=sys.stderr, flush=True)
            return

        with self._lock:
            try:
                path = self._get_asset_path(name)
                img = Image.open(path)

                # Ensure correct size
                if img.size != (WIDTH, HEIGHT):
                    img = img.resize((WIDTH, HEIGHT))

                # Convert to 1-bit if needed
                if img.mode != '1':
                    img = img.convert('1')

                self.epd.display(self.epd.getbuffer(img))
                self.current_state = name
                print(f"[EYES] Displayed: {name}", file=sys.stderr, flush=True)

            except Exception as e:
                print(f"[EYES] Error displaying {name}: {e}", file=sys.stderr, flush=True)

    def sleep(self):
        """Go to sleep (closed eyes)"""
        self._show_image('sleep')

    def wake(self):
        """Wake up animation"""
        self._show_image('wake_0')
        time.sleep(0.15)
        self._show_image('wake_1')
        time.sleep(0.15)
        self._show_image('awake')

    def awake(self):
        """Show awake state"""
        self._show_image('awake')

    def blink(self):
        """Quick blink"""
        self._show_image('blink')
        time.sleep(0.15)
        self._show_image('awake')

    def focus(self):
        """Concentrating/narrowed eyes"""
        self._show_image('focus')

    def close(self):
        """Clean shutdown"""
        if self._enabled and self.epd:
            try:
                self.epd.sleep()
            except:
                pass


# Singleton instance
_eyes = None

def get_eyes():
    """Get or create the eyes singleton"""
    global _eyes
    if _eyes is None:
        _eyes = PrinterEyes()
    return _eyes


if __name__ == '__main__':
    import sys
    # Test
    eyes = get_eyes()
    print("Testing eye states...", file=sys.stderr, flush=True)
    time.sleep(1)

    print("Waking...", file=sys.stderr, flush=True)
    eyes.wake()
    time.sleep(2)

    print("Blink...", file=sys.stderr, flush=True)
    eyes.blink()
    time.sleep(1)

    print("Focus...", file=sys.stderr, flush=True)
    eyes.focus()
    time.sleep(1)

    print("Sleeping...", file=sys.stderr, flush=True)
    eyes.sleep()

    eyes.close()
