#!/usr/bin/env python3
"""
Thermal Printer Server for ORGSTA T001
"""

import base64
import http.server
import io
import json
import os
import random
import socketserver
import sys
import time
import traceback
from datetime import datetime
from urllib.parse import parse_qs, urlparse

from PIL import Image

# Optional: Printer eyes (eInk display)
try:
    from printer_eyes import get_eyes
    eyes = get_eyes()
except Exception as e:
    eyes = None


def env_bool(name, default=False):
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def env_int(name, default):
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def env_float(name, default):
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def dedupe(items):
    out = []
    seen = set()
    for item in items:
        if not item:
            continue
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


PORT = env_int("THERMAL_PORT", 8765)
PRINTER_DPI = env_int("THERMAL_DPI", 203)
GAP_MM = env_float("THERMAL_GAP_MM", 3.0)
MM_PER_INCH = 25.4

# Label configuration for 4" x 6" labels
LABEL_WIDTH_MM = env_float("THERMAL_LABEL_WIDTH_MM", 101.6)
LABEL_HEIGHT_MM = env_float("THERMAL_LABEL_HEIGHT_MM", 152.4)
X_OFFSET = env_int("THERMAL_X_OFFSET", 0)
Y_OFFSET = env_int("THERMAL_Y_OFFSET", 0)

# Default is OFF so full-page stickers keep their original canvas/bleed.
AUTO_TRIM_TOP_WHITESPACE = env_bool("THERMAL_AUTO_TRIM_TOP_WHITESPACE", False)
WHITE_THRESHOLD = env_int("THERMAL_WHITE_THRESHOLD", 245)
MAX_TOP_TRIM_PX = env_int("THERMAL_MAX_TOP_TRIM_PX", 80)
HORIZONTAL_SHIFT_PX = env_int("THERMAL_HORIZONTAL_SHIFT_PX", -20)

_env_candidates = os.getenv("THERMAL_DEVICE_CANDIDATES", "").replace(",", ":").split(":")
PRINTER_DEVICE_CANDIDATES = dedupe(
    [os.getenv("THERMAL_DEVICE_PATH", "").strip()]
    + [c.strip() for c in _env_candidates]
    + ["/dev/thermal-printer", "/dev/usb/lp0", "/dev/usb/lp1", "/dev/usb/lp2"]
)


def log_event(level, message, **fields):
    payload = {"level": level, "message": message}
    if fields:
        payload.update(fields)
    print(json.dumps(payload, sort_keys=True), file=sys.stderr, flush=True)


def current_printer_device():
    for path in PRINTER_DEVICE_CANDIDATES:
        if os.path.exists(path):
            return path
    return None


def printer_health():
    device_path = current_printer_device()
    return {
        "service": "ok",
        "printer_connected": bool(device_path),
        "printer_device": device_path,
        "device_candidates": PRINTER_DEVICE_CANDIDATES,
        "label": {
            "width_mm": LABEL_WIDTH_MM,
            "height_mm": LABEL_HEIGHT_MM,
            "gap_mm": GAP_MM,
            "pitch_mm": LABEL_HEIGHT_MM + GAP_MM,
            "dpi": PRINTER_DPI,
        },
        "image_processing": {
            "x_offset": X_OFFSET,
            "y_offset": Y_OFFSET,
            "horizontal_shift_px": HORIZONTAL_SHIFT_PX,
            "auto_trim_top_whitespace": AUTO_TRIM_TOP_WHITESPACE,
            "white_threshold": WHITE_THRESHOLD,
            "max_top_trim_px": MAX_TOP_TRIM_PX,
        },
    }


def labels_to_dots(labels):
    return max(1, round(labels * (LABEL_HEIGHT_MM + GAP_MM) * PRINTER_DPI / MM_PER_INCH))


def parse_rewind_request(path, body):
    query = parse_qs(urlparse(path).query)
    raw_text = body.decode("utf-8", errors="ignore").strip()

    labels = None
    dots = None
    dry_run = False

    if raw_text:
        try:
            payload = json.loads(raw_text)
            if isinstance(payload, dict):
                labels = payload.get("labels")
                dots = payload.get("dots")
                dry_run = bool(payload.get("dry_run", False))
            elif isinstance(payload, (int, float)):
                labels = payload
        except json.JSONDecodeError:
            # Plain numeric body means labels.
            try:
                labels = float(raw_text)
            except ValueError:
                pass

    if "labels" in query:
        labels = query["labels"][-1]
    if "dots" in query:
        dots = query["dots"][-1]
    if "dry_run" in query:
        dry_run = query["dry_run"][-1].strip().lower() in {"1", "true", "yes", "on"}

    if labels is not None:
        try:
            labels = float(labels)
        except (TypeError, ValueError) as exc:
            raise ValueError("rewind labels must be numeric") from exc

    if dots is not None:
        try:
            dots = int(float(dots))
        except (TypeError, ValueError) as exc:
            raise ValueError("rewind dots must be numeric") from exc

    if labels is None and dots is None:
        raise ValueError("Provide rewind labels or dots")

    if labels is not None and labels <= 0:
        raise ValueError("rewind labels must be > 0")
    if dots is not None and dots <= 0:
        raise ValueError("rewind dots must be > 0")

    if labels is not None and labels > 50:
        raise ValueError("rewind labels too large (max 50)")
    if dots is not None and dots > 200000:
        raise ValueError("rewind dots too large (max 200000)")

    computed_dots = dots if dots is not None else labels_to_dots(labels)
    computed_labels = labels if labels is not None else round(
        computed_dots * MM_PER_INCH / ((LABEL_HEIGHT_MM + GAP_MM) * PRINTER_DPI), 4
    )

    return {
        "labels": computed_labels,
        "dots": computed_dots,
        "dry_run": dry_run,
        "pitch_mm": LABEL_HEIGHT_MM + GAP_MM,
        "dpi": PRINTER_DPI,
    }


class PrinterWriteError(Exception):
    def __init__(self, code, message, status=503, **details):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.details = details

    def to_dict(self):
        payload = {"error": self.message, "code": self.code}
        payload.update(self.details)
        return payload


def trim_top_whitespace(img):
    """Optionally trim blank rows by shifting content up while preserving canvas size."""
    if not AUTO_TRIM_TOP_WHITESPACE:
        return img

    mask = img.point(lambda p: 255 if p < WHITE_THRESHOLD else 0, "1")
    bbox = mask.getbbox()
    if not bbox:
        return img

    top = bbox[1]
    if top <= 0:
        return img

    trim_px = min(top, MAX_TOP_TRIM_PX)
    width, height = img.size
    if trim_px >= height:
        return img

    shifted = Image.new("L", (width, height), 255)
    source = img.crop((0, trim_px, width, height))
    shifted.paste(source, (0, 0))
    return shifted


def shift_image_horizontally(img, shift_px):
    """Shift image content left/right while keeping canvas size constant."""
    if shift_px == 0:
        return img

    width, height = img.size
    if abs(shift_px) >= width:
        return Image.new("L", (width, height), 255)

    shifted = Image.new("L", (width, height), 255)
    if shift_px > 0:
        source = img.crop((0, 0, width - shift_px, height))
        shifted.paste(source, (shift_px, 0))
    else:
        shift_left = -shift_px
        source = img.crop((shift_left, 0, width, height))
        shifted.paste(source, (0, 0))

    return shifted


def image_to_tspl(image_data, x=X_OFFSET, y=Y_OFFSET, dither=True):
    """Convert image to TSPL BITMAP command with raw binary data."""
    img = Image.open(io.BytesIO(image_data)).convert("L")
    img = trim_top_whitespace(img)
    img = shift_image_horizontally(img, HORIZONTAL_SHIFT_PX)

    width, height = img.size
    img = Image.eval(img, lambda p: 255 - p)

    if dither:
        img = img.convert("1", dither=Image.Dither.FLOYDSTEINBERG)
    else:
        img = img.point(lambda p: 0 if p < 128 else 255, "1")

    width_bytes = (width + 7) // 8
    padded_width = width_bytes * 8
    pixels = list(img.getdata())

    bitmap_bytes = bytearray()
    for row in range(height):
        row_start = row * width
        for byte_col in range(0, padded_width, 8):
            byte_val = 0
            for bit in range(8):
                pixel_col = byte_col + bit
                if pixel_col < width and pixels[row_start + pixel_col] < 128:
                    byte_val |= 1 << (7 - bit)
            bitmap_bytes.append(byte_val)

    header = f"BITMAP {x},{y},{width_bytes},{height},0,"
    return header, bytes(bitmap_bytes)


class LabelTemplates:
    @staticmethod
    def standard_shipping(order, customer, address, barcode=None, date_str=None):
        if date_str is None:
            date_str = datetime.now().strftime("%Y-%m-%d")

        tspl = [
            f"SIZE {LABEL_WIDTH_MM}mm,{LABEL_HEIGHT_MM}mm",
            "GAP 3mm,0mm",
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

        if "," in address:
            addr_lines = address.split(",")
        else:
            addr_lines = [address[i:i + 30] for i in range(0, min(len(address), 90), 30)]
        y = 330
        for line in addr_lines[:3]:
            safe_line = line.strip().replace('"', '\\"')[:35]
            tspl.append(f'TEXT 70,{y},"2",0,1,1,"{safe_line}"')
            y += 50

        bc = barcode if barcode else order
        tspl.extend(
            [
                "BAR 40,500,360,2",
                f'BARCODE 80,520,"128",80,1,0,2,2,"{bc[:25]}"',
                f'TEXT 80,620,"1",0,1,1,"{bc[:25]}"',
            ]
        )

        tspl.append("PRINT 1,1")
        return "\n".join(tspl)

    @staticmethod
    def simple_text(lines, title="ATK FABRICATION"):
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


def _write_printer(payload):
    device_path = current_printer_device()
    if not device_path:
        raise PrinterWriteError(
            "printer_device_missing",
            "No thermal printer device found",
            status=503,
            device_candidates=PRINTER_DEVICE_CANDIDATES,
        )

    try:
        with open(device_path, "wb") as device:
            device.write(payload)
        return device_path
    except FileNotFoundError as exc:
        raise PrinterWriteError(
            "printer_device_missing",
            str(exc),
            status=503,
            device_path=device_path,
            device_candidates=PRINTER_DEVICE_CANDIDATES,
        ) from exc
    except PermissionError as exc:
        raise PrinterWriteError(
            "printer_device_permission_denied",
            str(exc),
            status=500,
            device_path=device_path,
        ) from exc
    except OSError as exc:
        raise PrinterWriteError(
            "printer_device_io_error",
            str(exc),
            status=500,
            device_path=device_path,
            errno=getattr(exc, "errno", None),
        ) from exc


def send_tspl(tspl_data):
    return _write_printer((tspl_data + "\n").encode())


def send_tspl_bytes(tspl_bytes):
    return _write_printer(tspl_bytes)


def help_text():
    return f"""Thermal Label Printer API - ATK Fabrication

LABEL SIZE: {LABEL_WIDTH_MM}mm x {LABEL_HEIGHT_MM}mm (4\" x 6\")
GAP DETECTION: Enabled (3mm) for label media
DEVICE CANDIDATES: {", ".join(PRINTER_DEVICE_CANDIDATES)}
AUTO TRIM TOP WHITESPACE: {AUTO_TRIM_TOP_WHITESPACE}

ENDPOINTS:
GET  /healthz     - Service + printer device status
POST /rewind      - Reverse feed ({round(labels_to_dots(1))} dots ~= 1 label pitch)
POST /print       - Simple text (body: "Line 1\\nLine 2")
POST /shipping    - Shipping label (body: "order|customer|address|barcode")
POST /packing     - Packing list (body: "order|customer|item1,item2,item3")
POST /raw         - Raw TSPL commands
POST /image       - Base64-encoded PNG/JPG image

EXAMPLES:
curl -X POST http://thermal.local:8765/shipping -d "54321|Jane Doe|123 Oak Ave, Detroit|ORDER54321"
curl -X POST http://thermal.local:8765/image -d "$(base64 -i logo.png)"
curl -X POST http://thermal.local:8765/rewind -d '{"labels":2}'
"""


class Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, fmt, *args):
        log_event("info", "http_request", client=self.client_address[0], path=self.path, detail=(fmt % args))

    def send_json(self, data, code=200):
        payload = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def send_text(self, text, code=200):
        payload = text.encode()
        self.send_response(code)
        self.send_header("Content-type", "text/plain")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _decode_body_text(self, body):
        try:
            return body.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("Request body must be UTF-8") from exc

    def _with_eyes(self, fn, focus=False):
        """Wrap a function with eye wake/sleep animation"""
        if eyes:
            if focus:
                eyes.focus()
            else:
                eyes.wake()
        try:
            return fn()
        finally:
            if eyes:
                eyes.sleep()

    def do_POST(self):
        route = urlparse(self.path).path
        content_len = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_len)

        try:
            if route == "/print":
                def do_print():
                    lines = self._decode_body_text(body).strip().split("\n")
                    device_path = send_tspl(LabelTemplates.simple_text(lines))
                    self.send_json({"status": "printed", "lines": len(lines), "template": "simple", "device_path": device_path})
                self._with_eyes(do_print)
                return

            if route == "/shipping":
                def do_shipping():
                    parts = self._decode_body_text(body).strip().split("|")
                    if len(parts) < 3:
                        self.send_json({"error": "Format: order|customer|address|barcode", "code": "bad_request"}, 400)
                        return
                    order, customer, address = parts[0], parts[1], parts[2]
                    barcode = parts[3] if len(parts) > 3 else order
                    device_path = send_tspl(LabelTemplates.standard_shipping(order, customer, address, barcode))
                    self.send_json({"status": "printed", "order": order, "template": "shipping", "device_path": device_path})
                self._with_eyes(do_shipping)
                return

            if route == "/packing":
                def do_packing():
                    parts = self._decode_body_text(body).strip().split("|")
                    if len(parts) < 3:
                        self.send_json({"error": "Format: order|customer|item1,item2,item3", "code": "bad_request"}, 400)
                        return
                    order, customer = parts[0], parts[1]
                    items = parts[2].split(",")
                    device_path = send_tspl(LabelTemplates.packing_list(order, items, customer))
                    self.send_json(
                        {"status": "printed", "order": order, "template": "packing", "items": len(items), "device_path": device_path}
                    )
                self._with_eyes(do_packing)
                return

            if route == "/raw":
                def do_raw():
                    device_path = send_tspl(self._decode_body_text(body))
                    self.send_json({"status": "printed", "mode": "raw", "device_path": device_path})
                self._with_eyes(do_raw)
                return

            if route == "/rewind":
                req = parse_rewind_request(self.path, body)
                tspl = f"BACKFEED {req['dots']}"
                device_path = None
                if not req["dry_run"]:
                    # 30% chance to do a suspicious sweep during rewind
                    if eyes and random.random() < 0.3:
                        eyes.sweep()
                    elif eyes:
                        eyes.focus()
                    try:
                        device_path = send_tspl(tspl)
                    finally:
                        if eyes:
                            eyes.sleep()
                self.send_json(
                    {
                        "status": "ok" if req["dry_run"] else "printed",
                        "mode": "rewind",
                        "labels": req["labels"],
                        "dots": req["dots"],
                        "pitch_mm": req["pitch_mm"],
                        "dpi": req["dpi"],
                        "tspl": tspl,
                        "dry_run": req["dry_run"],
                        "device_path": device_path,
                    }
                )
                return

            if route == "/image":
                def do_image():
                    try:
                        image_data = base64.b64decode(body, validate=False)
                        header, bitmap_data = image_to_tspl(image_data)
                        output = bytearray()
                        output.extend(f"SIZE {LABEL_WIDTH_MM}mm,{LABEL_HEIGHT_MM}mm\n".encode())
                        output.extend(b"GAP 3mm,0mm\n")
                        output.extend(b"CLS\n")
                        output.extend(header.encode("ascii"))
                        output.extend(bitmap_data)
                        output.extend(b"\nPRINT 1,1\n")
                        device_path = send_tspl_bytes(output)
                        self.send_json({"status": "printed", "template": "image", "device_path": device_path})
                    except PrinterWriteError:
                        raise
                    except Exception as exc:
                        self.send_json(
                            {"error": f"Image processing failed: {exc}", "code": "image_processing_failed"},
                            500,
                        )
                self._with_eyes(do_image)
                return

            self.send_error(404)

        except PrinterWriteError as exc:
            if eyes:
                eyes.surprise()
            log_event("error", "printer_write_failed", route=route, **exc.to_dict())
            self.send_json(exc.to_dict(), exc.status)
            if eyes:
                time.sleep(1)
                eyes.sleep()
        except ValueError as exc:
            self.send_json({"error": str(exc), "code": "bad_request"}, 400)
        except Exception as exc:
            if eyes:
                eyes.surprise()
            log_event("error", "unhandled_exception", route=route, error=str(exc), traceback=traceback.format_exc())
            self.send_json({"error": "Internal server error", "code": "internal_error"}, 500)
            if eyes:
                time.sleep(1)
                eyes.sleep()

    def do_GET(self):
        route = urlparse(self.path).path
        if route == "/healthz":
            health = printer_health()
            health["status"] = "ok" if health["printer_connected"] else "degraded"
            self.send_json(health, 200)
            return

        if route == "/":
            self.send_text(help_text(), 200)
            return

        self.send_error(404)


class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    daemon_threads = True
    allow_reuse_address = True


if __name__ == "__main__":
    with ThreadedTCPServer(("0.0.0.0", PORT), Handler) as httpd:
        log_event(
            "info",
            "server_start",
            port=PORT,
            label_width_mm=LABEL_WIDTH_MM,
            label_height_mm=LABEL_HEIGHT_MM,
            device_candidates=PRINTER_DEVICE_CANDIDATES,
            auto_trim_top_whitespace=AUTO_TRIM_TOP_WHITESPACE,
        )
        httpd.serve_forever()
