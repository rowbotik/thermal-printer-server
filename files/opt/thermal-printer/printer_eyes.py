"""
Printer Eyes - eInk display controller for 2.13" V4 (250x122)
Retro pixelated style with personality
"""

import os
import time
import threading
import random
from PIL import Image

# Try to import waveshare eInk library
try:
    import sys
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

ASSET_DIR = os.path.join(os.path.dirname(__file__), 'eyes_assets')
WIDTH, HEIGHT = 250, 122

# Pixel art eye templates (low res, will be scaled up)
# 0 = black, 1 = white
EYE_TEMPLATES = {
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
}


class PrinterEyes:
    """Retro pixelated eye controller for thermal printer"""

    def __init__(self):
        self.epd = None
        self.current_state = None
        self._lock = threading.Lock()
        self._enabled = HAS_EINK
        self._idle_thread = None
        self._idle_running = False

        if self._enabled:
            try:
                self.epd = epd2in13_V4.EPD()
                self.epd.init()
                self.epd.Clear()
                print("[EYES] eInk display initialized", file=sys.stderr, flush=True)
                self._show_image('sleep')
                self._start_idle()
            except Exception as e:
                print(f"[EYES] Failed to init display: {e}", file=sys.stderr, flush=True)
                self._enabled = False

    def _pixel_art_to_image(self, template, scale=6):
        """Convert ASCII art to pixelated image"""
        lines = template if isinstance(template, list) else template.split('\n')
        lines = [l for l in lines if l.strip()]
        
        h = len(lines)
        w = max(len(l) for l in lines) if lines else 20
        
        # Create low-res image
        img = Image.new('1', (w, h), 1)
        pixels = img.load()
        
        for y, line in enumerate(lines):
            for x, char in enumerate(line):
                if char == 'X':
                    pixels[x, y] = 0  # Black
        
        # Scale up with nearest neighbor (pixelated look)
        img = img.resize((w * scale, h * scale), Image.NEAREST)
        
        # Center on 250x122 display
        final = Image.new('1', (WIDTH, HEIGHT), 1)
        x_off = (WIDTH - img.width) // 2
        y_off = (HEIGHT - img.height) // 2
        final.paste(img, (x_off, y_off))
        
        return final

    def _generate_asset(self, name):
        """Generate pixelated eye image"""
        os.makedirs(ASSET_DIR, exist_ok=True)
        path = os.path.join(ASSET_DIR, f'{name}.bmp')
        
        if name in EYE_TEMPLATES:
            img = self._pixel_art_to_image(EYE_TEMPLATES[name])
        elif name == 'wake_0':
            # Half-open
            img = self._pixel_art_to_image([
                "                        ",
                "                        ",
                "      XXXXXXXX          XXXXXXXX      ",
                "     XXXXXXXXXX        XXXXXXXXXX     ",
                "                        ",
                "                        ",
                "      XXXXXXXX          XXXXXXXX      ",
                "                        ",
                "                        ",
            ])
        elif name == 'wake_1':
            # 75% open
            img = self._pixel_art_to_image([
                "                        ",
                "                        ",
                "      XXXXXXXX          XXXXXXXX      ",
                "     XXXXXXXXXX        XXXXXXXXXX     ",
                "     XXXXXXXXXX        XXXXXXXXXX     ",
                "     XXXXXXXXXX        XXXXXXXXXX     ",
                "      XXXXXXXX          XXXXXXXX      ",
                "                        ",
                "                        ",
            ])
        elif name == 'focus':
            # Narrowed
            img = self._pixel_art_to_image([
                "                        ",
                "                        ",
                "                        ",
                "      XXXXXXXX          XXXXXXXX      ",
                "     XXXX  XXXX        XXXX  XXXX     ",
                "      XXXXXXXX          XXXXXXXX      ",
                "                        ",
                "                        ",
                "                        ",
            ])
        else:
            # Default to sleep
            img = self._pixel_art_to_image(EYE_TEMPLATES['sleep'])
        
        img.save(path)
        return path

    def _get_asset_path(self, name):
        """Get path to BMP asset"""
        path = os.path.join(ASSET_DIR, f'{name}.bmp')
        if os.path.exists(path):
            return path
        return self._generate_asset(name)

    def _show_image(self, name):
        """Display an image by name"""
        if not self._enabled:
            print(f"[EYES] Would show: {name}", file=sys.stderr, flush=True)
            return

        with self._lock:
            try:
                path = self._get_asset_path(name)
                img = Image.open(path)
                if img.size != (WIDTH, HEIGHT):
                    img = img.resize((WIDTH, HEIGHT))
                if img.mode != '1':
                    img = img.convert('1')
                self.epd.display(self.epd.getbuffer(img))
                self.current_state = name
                print(f"[EYES] {name}", file=sys.stderr, flush=True)
            except Exception as e:
                print(f"[EYES] Error: {e}", file=sys.stderr, flush=True)

    def _start_idle(self):
        """Start idle animation thread"""
        self._idle_running = True
        self._idle_thread = threading.Thread(target=self._idle_loop, daemon=True)
        self._idle_thread.start()

    def _idle_loop(self):
        """Random idle behaviors while awake"""
        while self._idle_running:
            time.sleep(random.uniform(3, 8))
            if self.current_state == 'awake' and self._enabled:
                action = random.choice(['blink', 'look_left', 'look_right', 'look_up', None])
                if action:
                    if action == 'blink':
                        self._show_image('blink')
                        time.sleep(0.15)
                        self._show_image('awake')
                    else:
                        self._show_image(action)
                        time.sleep(0.5)
                        self._show_image('awake')

    def sleep(self):
        """Closed eyes"""
        self._show_image('sleep')

    def wake(self):
        """Animated wake with personality"""
        # Randomly open one eye first
        if random.random() < 0.3:
            self._show_image('one_eye')
            time.sleep(0.4)
        self._show_image('wake_0')
        time.sleep(0.2)
        self._show_image('wake_1')
        time.sleep(0.15)
        self._show_image('awake')

    def awake(self):
        """Open eyes"""
        self._show_image('awake')

    def blink(self):
        """Quick blink"""
        self._show_image('blink')
        time.sleep(0.15)
        self._show_image('awake')

    def focus(self):
        """Narrowed eyes for concentration"""
        self._show_image('focus')

    def sweep(self):
        """Look left then right (suspicious/curious)"""
        self._show_image('look_left')
        time.sleep(0.3)
        self._show_image('look_right')
        time.sleep(0.3)
        self._show_image('awake')

    def surprise(self):
        """Wide eyes"""
        self._show_image('surprised')

    def suspicious(self):
        """Side-eye glance"""
        self._show_image('suspicious')

    def close(self):
        """Shutdown"""
        self._idle_running = False
        if self._enabled and self.epd:
            try:
                self.epd.sleep()
            except:
                pass


_eyes = None

def get_eyes():
    global _eyes
    if _eyes is None:
        _eyes = PrinterEyes()
    return _eyes


if __name__ == '__main__':
    import sys
    eyes = get_eyes()
    print("Testing personality...", file=sys.stderr)
    
    time.sleep(1)
    print("Wake...", file=sys.stderr)
    eyes.wake()
    time.sleep(2)
    
    print("Sweep...", file=sys.stderr)
    eyes.sweep()
    time.sleep(1)
    
    print("Suspicious...", file=sys.stderr)
    eyes.suspicious()
    time.sleep(1)
    
    print("Sleep...", file=sys.stderr)
    eyes.sleep()
    eyes.close()
