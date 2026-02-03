#!/usr/bin/env python3
"""
Thermal Printer Server for ORGSTA T001
Flask version with Web UI for configuration
"""

import os
import json
import shutil
import subprocess
import base64
import io
from datetime import datetime
from typing import Dict, Any

from flask import Flask, request, jsonify, Response
from PIL import Image

app = Flask(__name__)

# Config paths
CONFIG_PATH = "/home/alex/thermal_config.json"
PRINTER_DEVICE = "/dev/usb/lp0"

# Constants
DOTS_PER_MM = 8
DOT_MIN = -300
DOT_MAX = 300

# Default config (4" x 6" labels)
DEFAULT_CONFIG = {
    "label_width_mm": 101.6,
    "label_height_mm": 152.4,
    "gap_mm": 2.5,
    "x_offset": 32,
    "y_offset": 0
}

def load_config():
    if not os.path.exists(CONFIG_PATH):
        return DEFAULT_CONFIG.copy()
    try:
        with open(CONFIG_PATH, "r") as f:
            data = json.load(f)
        out = DEFAULT_CONFIG.copy()
        out.update({k: data.get(k, v) for k, v in DEFAULT_CONFIG.items()})
        return out
    except Exception:
        return DEFAULT_CONFIG.copy()

def save_config(cfg):
    if os.path.exists(CONFIG_PATH):
        shutil.copyfile(CONFIG_PATH, CONFIG_PATH + ".bak")
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)

def send_tspl(tspl_data):
    with open(PRINTER_DEVICE, "wb") as f:
        f.write((tspl_data + "\n").encode())

def send_tspl_bytes(tspl_bytes):
    with open(PRINTER_DEVICE, "wb") as f:
        f.write(tspl_bytes)

def image_to_tspl(image_data, x=0, y=0, dither=True):
    img = Image.open(io.BytesIO(image_data)).convert("L")
    width, height = img.size
    img = Image.eval(img, lambda px: 255 - px)
    if dither:
        img = img.convert("1", dither=Image.Dither.FLOYDSTEINBERG)
    else:
        img = img.point(lambda px: 0 if px < 128 else 255, "1")
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
                if pixel_col < width:
                    pixel_val = pixels[row_start + pixel_col]
                    if pixel_val < 128:
                        byte_val |= (1 << (7 - bit))
            bitmap_bytes.append(byte_val)
    header = f"BITMAP {x},{y},{width_bytes},{height},0,"
    return header, bytes(bitmap_bytes)

class LabelTemplates:
    @staticmethod
    def tspl_header(cfg):
        return f"SIZE {cfg['label_width_mm']} mm,{cfg['label_height_mm']} mm\nGAP {cfg['gap_mm']} mm,0\nDENSITY 8\nSPEED 4\nDIRECTION 1\nSHIFT {int(cfg['x_offset'])}\nCLS\n"
    
    @staticmethod
    def simple_text(lines, title="ATK FABRICATION", cfg=None):
        if cfg is None:
            cfg = load_config()
        y0 = int(cfg["y_offset"])
        tspl = LabelTemplates.tspl_header(cfg)
        tspl += f'TEXT 50,{30+y0},"3",0,1,1,"{title}"\n'
        tspl += f"BAR 50,{80+y0},400,4\n"
        y = 110 + y0
        for line in lines[:8]:
            safe = line.replace('"', '\\"')[:40]
            tspl += f'TEXT 50,{y},"2",0,1,1,"{safe}"\n'
            y += 55
        tspl += "PRINT 1,1\n"
        return tspl
    
    @staticmethod
    def border_test(cfg=None):
        if cfg is None:
            cfg = load_config()
        w = int(round(cfg["label_width_mm"] * DOTS_PER_MM))
        h = int(round(cfg["label_height_mm"] * DOTS_PER_MM))
        y0 = int(cfg["y_offset"])
        tspl = LabelTemplates.tspl_header(cfg)
        tspl += f"BOX 0,{y0},{w-1},{y0 + h-1},2\n"
        tspl += f'TEXT 10,{y0+10},"0",0,1,1,"BORDER TEST"\n'
        tspl += f"PRINT 1\n"
        return tspl
    
    @staticmethod
    def center_test(cfg=None):
        if cfg is None:
            cfg = load_config()
        w = int(round(cfg["label_width_mm"] * DOTS_PER_MM))
        h = int(round(cfg["label_height_mm"] * DOTS_PER_MM))
        cx = w // 2
        cy = (h // 2) + int(cfg["y_offset"])
        y0 = int(cfg["y_offset"])
        tspl = LabelTemplates.tspl_header(cfg)
        tspl += f"BAR {cx-20},{cy-1},40,2\n"
        tspl += f"BAR {cx-1},{cy-20},2,40\n"
        tspl += f"BOX {cx-32},{cy-32},{cx+32},{cy+32},1\n"
        tspl += f"BOX {cx-16},{cy-16},{cx+16},{cy+16},1\n"
        tspl += f'TEXT 10,{y0+10},"0",0,1,1,"CENTER CAL"\n'
        tspl += f"PRINT 1\n"
        return tspl

@app.route("/api/config", methods=["GET", "POST"])
def api_config():
    if request.method == "GET":
        return jsonify(load_config())
    payload = request.get_json(force=True, silent=True)
    if not payload:
        return jsonify({"error": "Invalid JSON"}), 400
    current = load_config()
    merged = current.copy()
    for k in DEFAULT_CONFIG.keys():
        if k in payload:
            merged[k] = payload[k]
    try:
        merged["x_offset"] = int(merged["x_offset"])
        merged["y_offset"] = int(merged["y_offset"])
        merged["label_width_mm"] = float(merged["label_width_mm"])
        merged["label_height_mm"] = float(merged["label_height_mm"])
        merged["gap_mm"] = float(merged["gap_mm"])
    except (ValueError, TypeError) as e:
        return jsonify({"error": f"Invalid value: {e}"}), 400
    save_config(merged)
    return jsonify(merged)

@app.route("/api/nudge", methods=["POST"])
def api_nudge():
    payload = request.get_json(force=True, silent=True)
    if not payload:
        return jsonify({"error": "Invalid JSON"}), 400
    axis = payload.get("axis")
    mm = payload.get("mm")
    if axis not in ("x", "y"):
        return jsonify({"error": "axis must be 'x' or 'y'"}), 400
    try:
        mm = float(mm)
    except (ValueError, TypeError):
        return jsonify({"error": "mm must be a number"}), 400
    cfg = load_config()
    delta_dots = int(round(mm * DOTS_PER_MM))
    if axis == "x":
        cfg["x_offset"] = max(DOT_MIN, min(DOT_MAX, int(cfg["x_offset"]) + delta_dots))
    else:
        cfg["y_offset"] = max(DOT_MIN, min(DOT_MAX, int(cfg["y_offset"]) + delta_dots))
    save_config(cfg)
    return jsonify(cfg)

@app.route("/api/print-test/<test_type>", methods=["POST"])
def api_print_test(test_type):
    cfg = load_config()
    if test_type == "border":
        send_tspl(LabelTemplates.border_test(cfg))
    elif test_type == "center":
        send_tspl(LabelTemplates.center_test(cfg))
    else:
        return jsonify({"error": "Unknown test type"}), 400
    return jsonify({"ok": True, "test": test_type})

@app.route("/api/restart", methods=["POST"])
def api_restart():
    try:
        subprocess.run(["sudo", "systemctl", "restart", "thermal-print-server"], check=True)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/print", methods=["POST"])
def print_simple():
    lines = request.get_data().decode("utf-8").strip().split("\n")
    tspl = LabelTemplates.simple_text(lines)
    send_tspl(tspl)
    return jsonify({"status": "printed", "lines": len(lines), "template": "simple"})

@app.route("/raw", methods=["POST"])
def print_raw():
    tspl = request.get_data().decode("utf-8")
    send_tspl(tspl)
    return jsonify({"status": "printed", "mode": "raw"})

ADMIN_HTML = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Thermal Printer Admin</title>
<style>
body { font-family: system-ui, sans-serif; margin: 20px; max-width: 700px; background: #f5f5f5; }
.card { background: white; padding: 16px; border-radius: 8px; margin-bottom: 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
.row { margin-bottom: 12px; display: flex; align-items: center; }
.row label { width: 140px; font-weight: 500; color: #555; }
input, select { width: 120px; padding: 6px; border: 1px solid #ddd; border-radius: 4px; }
button { padding: 8px 16px; margin: 4px; border: none; border-radius: 4px; background: #0066cc; color: white; cursor: pointer; }
button:hover { background: #0052a3; }
.status { padding: 12px; background: #e9ecef; border-radius: 4px; margin-top: 12px; font-family: monospace; font-size: 13px; }
</style>
</head>
<body>
<h2>Thermal Printer Admin</h2>
<div class="card">
<h3>Settings</h3>
<div class="row"><label>X Offset:</label><input id="x_offset" type="number"></div>
<div class="row"><label>Y Offset:</label><input id="y_offset" type="number"></div>
<div class="row"><label>Width (mm):</label><input id="label_width_mm" type="number" step="0.1"></div>
<div class="row"><label>Height (mm):</label><input id="label_height_mm" type="number" step="0.1"></div>
<div class="row"><label>Gap (mm):</label><input id="gap_mm" type="number" step="0.1"></div>
<button onclick="saveConfig()">Save</button>
</div>
<div class="card">
<h3>Nudge</h3>
<select id="step"><option value="0.5">0.5mm</option><option value="1" selected>1mm</option><option value="2">2mm</option></select>
<button onclick="nudge('x', -getStep())">Left</button>
<button onclick="nudge('x', getStep())">Right</button>
<button onclick="nudge('y', -getStep())">Up</button>
<button onclick="nudge('y', getStep())">Down</button>
</div>
<div class="card">
<h3>Test Prints</h3>
<button onclick="printTest('border')">Border</button>
<button onclick="printTest('center')">Center</button>
</div>
<div id="status" class="status">Ready</div>
<script>
async function loadConfig(){
  const r = await fetch("/api/config");
  const c = await r.json();
  ["x_offset","y_offset","label_width_mm","label_height_mm","gap_mm"].forEach(k=>{
    document.getElementById(k).value = c[k];
  });
}
function getStep(){ return parseFloat(document.getElementById("step").value); }
function setStatus(msg){ document.getElementById("status").textContent = new Date().toLocaleTimeString() + " - " + msg; }
async function saveConfig(){
  const body = {x_offset: parseInt(x_offset.value), y_offset: parseInt(y_offset.value), label_width_mm: parseFloat(label_width_mm.value), label_height_mm: parseFloat(label_height_mm.value), gap_mm: parseFloat(gap_mm.value)};
  const r = await fetch("/api/config", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)});
  setStatus(r.ok ? "Saved" : "Error");
  if(r.ok) loadConfig();
}
async function nudge(axis, mm){
  const r = await fetch("/api/nudge", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({axis, mm})});
  const data = await r.json();
  setStatus(r.ok ? `Nudged ${axis} by ${mm}mm` : "Error");
  if(r.ok) loadConfig();
}
async function printTest(kind){
  const r = await fetch("/api/print-test/" + kind, {method: "POST"});
  setStatus(r.ok ? "Print sent" : "Error");
}
loadConfig();
</script>
</body>
</html>"""

@app.route("/admin")
def admin_ui():
    return Response(ADMIN_HTML, mimetype="text/html")

@app.route("/")
def index():
    cfg = load_config()
    return Response(f"Thermal Printer API\nLabel: {cfg['label_width_mm']}x{cfg['label_height_mm']}mm\nOffsets: X={cfg['x_offset']} Y={cfg['y_offset']}\n\nEndpoints: /print, /raw, /admin", mimetype="text/plain")

if __name__ == "__main__":
    print("Thermal printer server on port 8765")
    print(f"Admin UI: http://thermal.local:8765/admin")
    app.run(host="0.0.0.0", port=8765, threaded=True)