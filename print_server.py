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
    
    if test_type == "direction":
        # Print direction markers at corners
        tspl = LabelTemplates.tspl_header(cfg)
        tspl += f'TEXT 10,10,"2",0,1,1,"<<< LEFT EDGE"
'
        tspl += f'TEXT 600,10,"2",0,1,1,"RIGHT EDGE >>>"
'
        tspl += f'TEXT 10,1100,"2",0,1,1,"<<< LEFT EDGE"
'
        tspl += f'TEXT 600,1100,"2",0,1,1,"RIGHT EDGE >>>"
'
        tspl += f'TEXT 300,550,"3",0,1,1,"^ TOP ^"
'
        tspl += f'TEXT 300,1050,"3",0,1,1,"v BOTTOM v"
'
        tspl += f'BAR 10,50,800,2
'
        tspl += f'BAR 10,1150,800,2
'
        tspl += f'BAR 50,10,2,1200
'
        tspl += f'BAR 750,10,2,1200
'
        tspl += "PRINT 1
"
        send_tspl(tspl)
        return jsonify({"ok": True, "test": "direction"})
    elif test_type == "border":
    cfg = load_config()
    if test_type == "border":
        send_tspl(LabelTemplates.border_test(cfg))
    elif test_type == "center":
        send_tspl(LabelTemplates.center_test(cfg))
    else:
        return jsonify({"error": "Unknown test type"}), 400
    return jsonify({"ok": True, "test": test_type})

@app.route("/api/feed", methods=["POST"])
def api_feed():
    """Feed or reset label position"""
    try:
        action = request.get_json().get('action', 'feed')
        cfg = load_config()
        if action == 'reset':
            # Reset to home position
            tspl = f"SIZE {cfg['label_width_mm']} mm,{cfg['label_height_mm']} mm
GAP {cfg['gap_mm']} mm,0
HOME
CLS
PRINT 1
"
            send_tspl(tspl)
            return jsonify({"ok": True, "action": "reset"})
        else:
            # Feed forward one label
            tspl = f"SIZE {cfg['label_width_mm']} mm,{cfg['label_height_mm']} mm
GAP {cfg['gap_mm']} mm,0
FEED {int(cfg['label_height_mm'])}
"
            send_tspl(tspl)
            return jsonify({"ok": True, "action": "feed"})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

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

@app.route("/image", methods=["POST"])
def print_image():
    try:
        body = request.get_data()
        image_data = base64.b64decode(body)
        cfg = load_config()
        header, bitmap_data = image_to_tspl(image_data, x=cfg['x_offset'], y=cfg['y_offset'])
        
        output = bytearray()
        output.extend(f"SIZE {cfg['label_width_mm']}mm,{cfg['label_height_mm']}mm\n".encode())
        output.extend(f"GAP {cfg['gap_mm']}mm,0mm\n".encode())
        output.extend(b"CLS\n")
        output.extend(header.encode('ascii'))
        output.extend(bitmap_data)
        output.extend(b"\nPRINT 1,1\n")
        
        send_tspl_bytes(output)
        return jsonify({"status": "printed", "template": "image"})
    except Exception as e:
        return jsonify({"error": f"Image processing failed: {str(e)}"}), 500


ADMIN_HTML = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Thermal Printer Admin</title>
  <style>
    body { 
      font-family: system-ui, -apple-system, sans-serif; 
      margin: 20px; 
      max-width: 900px; 
      background: #f5f5f5;
    }
    h2 { margin-top: 0; }
    .container { display: flex; gap: 20px; flex-wrap: wrap; }
    .panel { 
      background: white; 
      padding: 16px; 
      border-radius: 8px; 
      box-shadow: 0 1px 3px rgba(0,0,0,0.1);
      flex: 1;
      min-width: 300px;
    }
    .row { margin-bottom: 12px; display: flex; align-items: center; }
    .row label { width: 140px; font-weight: 500; color: #555; }
    input, select { 
      width: 100px; 
      padding: 6px; 
      border: 1px solid #ddd; 
      border-radius: 4px;
      font-size: 14px;
    }
    button { 
      padding: 8px 16px; 
      margin: 4px; 
      border: none; 
      border-radius: 4px; 
      background: #0066cc; 
      color: white; 
      cursor: pointer;
      font-size: 14px;
    }
    button:hover { background: #0052a3; }
    button.secondary { background: #6c757d; }
    button.secondary:hover { background: #5a6268; }
    button.danger { background: #dc3545; }
    button.danger:hover { background: #c82333; }
    .nudge-grid { 
      display: grid; 
      grid-template-columns: auto auto auto; 
      gap: 8px; 
      justify-content: start;
      margin: 10px 0;
    }
    .status { 
      padding: 12px; 
      background: #e9ecef; 
      border-radius: 4px; 
      margin-top: 12px; 
      font-family: monospace; 
      font-size: 13px;
    }
    .status.ok { background: #d4edda; color: #155724; }
    .status.error { background: #f8d7da; color: #721c24; }
    .visualizer {
      display: flex;
      flex-direction: column;
      align-items: center;
      padding: 20px;
      background: #fafafa;
      border-radius: 8px;
      margin: 15px 0;
    }
    .label-container {
      position: relative;
      background: white;
      border: 2px solid #333;
      box-shadow: 0 2px 8px rgba(0,0,0,0.1);
    }
    .content-box {
      position: absolute;
      background: rgba(0, 102, 204, 0.15);
      border: 2px dashed #0066cc;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 12px;
      color: #0066cc;
      transition: all 0.2s ease;
    }
    .origin-marker {
      position: absolute;
      top: -2px;
      left: -2px;
      width: 12px;
      height: 12px;
      background: #dc3545;
      border-radius: 50%;
      border: 2px solid white;
      box-shadow: 0 0 0 2px #dc3545;
      z-index: 10;
      font-size: 8px;
      color: white;
      display: flex;
      align-items: center;
      justify-content: center;
    }
    .axis-x {
      position: absolute;
      top: 0;
      left: 0;
      width: 100%;
      height: 1px;
      background: repeating-linear-gradient(90deg, #ccc 0, #ccc 5px, transparent 5px, transparent 10px);
      opacity: 0.5;
    }
    .axis-y {
      position: absolute;
      top: 0;
      left: 0;
      width: 1px;
      height: 100%;
      background: repeating-linear-gradient(0deg, #ccc 0, #ccc 5px, transparent 5px, transparent 10px);
      opacity: 0.5;
    }
    .content-box::after { content: "CONTENT"; font-weight: bold; }
    .margin-label {
      position: absolute;
      font-size: 11px;
      color: #666;
      background: rgba(255,255,255,0.9);
      padding: 2px 6px;
      border-radius: 3px;
      white-space: nowrap;
    }
    .margin-top { top: -25px; left: 50%; transform: translateX(-50%); }
    .margin-bottom { bottom: -25px; left: 50%; transform: translateX(-50%); }
    .margin-left { left: -50px; top: 50%; transform: translateY(-50%); }
    .margin-right { right: -50px; top: 50%; transform: translateY(-50%); }
    .arrow {
      position: absolute;
      font-size: 16px;
      color: #dc3545;
      font-weight: bold;
      display: none;
    }
    .arrow.show { display: block; }
    .arrow.up { top: -40px; left: 50%; transform: translateX(-50%); }
    .arrow.down { bottom: -40px; left: 50%; transform: translateX(-50%); }
    .arrow.left { left: -70px; top: 50%; transform: translateY(-50%); }
    .arrow.right { right: -70px; top: 50%; transform: translateY(-50%); }
    .measurements {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 10px;
      margin-top: 15px;
      padding: 10px;
      background: white;
      border-radius: 6px;
      font-size: 13px;
    }
    .measurement {
      display: flex;
      justify-content: space-between;
      padding: 5px 10px;
      background: #f8f9fa;
      border-radius: 4px;
    }
    .measurement .label { color: #666; }
    .measurement .value { font-weight: bold; color: #333; font-family: monospace; }
    .measurement.warning .value { color: #dc3545; }
    .legend {
      font-size: 12px;
      color: #666;
      margin-top: 10px;
      text-align: center;
    }
    .history-panel { margin-top: 15px; padding: 10px; background: #f8f9fa; border-radius: 6px; font-size: 12px; max-height: 200px; overflow-y: auto; }
    .history-title { font-weight: 600; color: #333; margin-bottom: 8px; display: flex; justify-content: space-between; align-items: center; }
    .history-item { padding: 4px 0; border-bottom: 1px solid #eee; display: flex; justify-content: space-between; }
    .history-clear { font-size: 10px; color: #666; cursor: pointer; background: none; border: 1px solid #ddd; padding: 2px 8px; border-radius: 3px; }
    .scale-info {
      font-size: 11px;
      color: #999;
      text-align: center;
      margin-top: 5px;
    }
  </style>
</head>
<body>
  <h2>🖨️ Thermal Printer Admin</h2>
  
  <div class="container">
    <div class="panel">
      <h3>Settings</h3>
      <div class="row"><label>X Offset (dots):</label><input id="x_offset" type="number" onchange="updateVisualizer()"></div>
      <div class="row"><label>Y Offset (dots):</label><input id="y_offset" type="number" onchange="updateVisualizer()"></div>
      <div class="row"><label>Label Width (mm):</label><input id="label_width_mm" type="number" step="0.1" onchange="updateVisualizer()"></div>
      <div class="row"><label>Label Height (mm):</label><input id="label_height_mm" type="number" step="0.1" onchange="updateVisualizer()"></div>
      <div class="row"><label>Gap (mm):</label><input id="gap_mm" type="number" step="0.1"></div>
      <button onclick="saveConfig()">💾 Save Settings</button>
      
      <h3 style="margin-top: 20px;">Nudge</h3>
      <div class="row">
        <label>Step size:</label>
        <select id="step">
          <option value="0.5">0.5 mm (4 dots)</option>
          <option value="1" selected>1.0 mm (8 dots)</option>
          <option value="2">2.0 mm (16 dots)</option>
          <option value="5">5.0 mm (40 dots)</option>
          <option value="10">10.0 mm (80 dots)</option>
        </select>
      </div>
      <div class="nudge-grid">
        <div></div>
        <button onclick="nudge('y', -getStep())">⬆️ Up</button>
        <div></div>
        <button onclick="nudge('x', -getStep())">⬅️ Left</button>
        <div style="text-align:center; font-size: 12px; color: #666;">Move</div>
        <button onclick="nudge('x', getStep())">Right ➡️</button>
        <div></div>
        <button onclick="nudge('y', getStep())">⬇️ Down</button>
        <div></div>
      </div>
      
      <h3 style="margin-top: 20px;">Test Prints</h3>
      <button onclick="printTest('direction')">🧭 Direction Test</button>
      <button onclick="printTest('border')">📦 Border</button>
      <button onclick="printTest('center')">🎯 Center</button>
      <button onclick="printTest('values')" class="secondary">📋 Values</button>
      
      <h3 style="margin-top: 20px;">Feed Control</h3>
      <button onclick="feedControl('feed')">⬇️ Feed Forward</button>
      <button onclick="feedControl('reset')" class="danger">🏠 Reset Position</button>
      
      <h3 style="margin-top: 20px;">Service</h3>
      <button onclick="restartService()" class="secondary">🔄 Restart Server</button>
    </div>
    
    <div class="panel">
      <h3>Label Visualizer</h3>
      <div class="visualizer">
        <div style="position: relative; margin-bottom: 10px;">
          <div style="font-size: 12px; color: #666;">▼ Origin (0,0) at top-left</div>
        </div>
        <div class="label-container" id="labelContainer">
          <div class="origin-marker" title="Origin (0,0)">●</div>
          <div class="axis-x"></div>
          <div class="axis-y"></div>
          <div class="content-box" id="contentBox"></div>
          <div class="margin-label margin-top" id="marginTop">Top: 0mm</div>
          <div class="margin-label margin-bottom" id="marginBottom">Bottom: 0mm</div>
          <div class="margin-label margin-left" id="marginLeft">Left: 0mm</div>
          <div class="margin-label margin-right" id="marginRight">Right: 0mm</div>
          <div class="arrow up" id="arrowUp">⬆️</div>
          <div class="arrow down" id="arrowDown">⬇️</div>
          <div class="arrow left" id="arrowLeft">⬅️</div>
          <div class="arrow right" id="arrowRight">➡️</div>
        </div>
        <div class="scale-info" id="scaleInfo">Scale: Not to scale</div>
      </div>
      
      <div class="measurements">
        <div class="measurement" id="measTop">
          <span class="label">Top Margin:</span>
          <span class="value" id="valTop">0.0 mm</span>
        </div>
        <div class="measurement" id="measBottom">
          <span class="label">Bottom Margin:</span>
          <span class="value" id="valBottom">0.0 mm</span>
        </div>
        <div class="measurement" id="measLeft">
          <span class="label">Left Margin:</span>
          <span class="value" id="valLeft">0.0 mm</span>
        </div>
        <div class="measurement" id="measRight">
          <span class="label">Right Margin:</span>
          <span class="value" id="valRight">0.0 mm</span>
        </div>
      </div>
      
      <div class="legend">
        Solid line = Label edge | Dashed blue = Content area<br>
        X Offset shifts content LEFT/RIGHT | Y Offset shifts content UP/DOWN
      </div>
    </div>
  </div>

  <div id="status" class="status">Ready</div>

<script>
const DOTS_PER_MM = 8;

function dotsToMm(dots) { return dots / DOTS_PER_MM; }
function mmToDots(mm) { return Math.round(mm * DOTS_PER_MM); }

async function loadConfig(){
  try {
    const r = await fetch('/api/config');
    const c = await r.json();
    ['x_offset','y_offset','label_width_mm','label_height_mm','gap_mm'].forEach(k=>{
      const el = document.getElementById(k);
      if(el) el.value = c[k];
    });
    updateVisualizer();
    setStatus('Config loaded');
  } catch(e) {
    setStatus('Error: ' + e.message, true);
  }
}

function getStep(){ return parseFloat(document.getElementById('step').value); }

function setStatus(msg, isError=false){
  const el = document.getElementById('status');
  el.textContent = new Date().toLocaleTimeString() + ' - ' + msg;
  el.className = 'status ' + (isError ? 'error' : 'ok');
}

function updateVisualizer() {
  const xOffset = parseInt(document.getElementById('x_offset').value) || 0;
  const yOffset = parseInt(document.getElementById('y_offset').value) || 0;
  const labelW = parseFloat(document.getElementById('label_width_mm').value) || 80;
  const labelH = parseFloat(document.getElementById('label_height_mm').value) || 40;
  
  const maxDisplayW = 300;
  const scale = Math.min(maxDisplayW / labelW, 6);
  const displayW = labelW * scale;
  const displayH = labelH * scale;
  
  // Content box size (represents printable area, smaller than label)
  const contentW = displayW * 0.6;
  const contentH = displayH * 0.6;
  
  // Convert offsets to pixels
  const xOffsetPx = (xOffset / DOTS_PER_MM) * scale;
  const yOffsetPx = (yOffset / DOTS_PER_MM) * scale;
  
  // Position from origin (top-left)
  // FLIPPED: visual shows what actually happens on paper
  // X positive = content shifts LEFT on paper (opposite of visual right)
  const defaultMarginPx = (50 / DOTS_PER_MM) * scale; // 50 dots default margin
  const contentLeft = defaultMarginPx - xOffsetPx;  // NEGATED - matches reality
  const contentTop = defaultMarginPx + yOffsetPx;
  
  const container = document.getElementById('labelContainer');
  const contentBox = document.getElementById('contentBox');
  
  container.style.width = displayW + 'px';
  container.style.height = displayH + 'px';
  
  contentBox.style.width = contentW + 'px';
  contentBox.style.height = contentH + 'px';
  contentBox.style.left = contentLeft + 'px';
  contentBox.style.top = contentTop + 'px';
  
  // Update axis labels to show offset direction
  const axisX = container.querySelector('.axis-x');
  const axisY = container.querySelector('.axis-y');
  if (axisX) axisX.style.transform = 'translateY(' + Math.max(0, yOffsetPx) + 'px)';
  if (axisY) axisY.style.transform = 'translateX(' + Math.max(0, xOffsetPx) + 'px)';
  
  // FLIPPED: X positive = content moves LEFT, so left margin shrinks
  const leftMargin = dotsToMm(-xOffset);  // NEGATED
  const contentW_mm = (contentW / scale);
  const rightMargin = labelW - contentW_mm - leftMargin;
  const topMargin = dotsToMm(yOffset);
  const contentH_mm = (contentH / scale);
  const bottomMargin = labelH - contentH_mm - topMargin;
  
  document.getElementById('marginTop').textContent = 'Top: ' + topMargin.toFixed(1) + 'mm';
  document.getElementById('marginBottom').textContent = 'Bottom: ' + bottomMargin.toFixed(1) + 'mm';
  document.getElementById('marginLeft').textContent = 'Left: ' + leftMargin.toFixed(1) + 'mm';
  document.getElementById('marginRight').textContent = 'Right: ' + rightMargin.toFixed(1) + 'mm';
  
  document.getElementById('valTop').textContent = topMargin.toFixed(1) + ' mm';
  document.getElementById('valBottom').textContent = bottomMargin.toFixed(1) + ' mm';
  document.getElementById('valLeft').textContent = leftMargin.toFixed(1) + ' mm';
  document.getElementById('valRight').textContent = rightMargin.toFixed(1) + ' mm';
  
  document.getElementById('measTop').classList.toggle('warning', topMargin < 0);
  document.getElementById('measBottom').classList.toggle('warning', bottomMargin < 0);
  document.getElementById('measLeft').classList.toggle('warning', leftMargin < 0);
  document.getElementById('measRight').classList.toggle('warning', rightMargin < 0);
  
  document.getElementById('arrowUp').classList.toggle('show', yOffset < 0);
  document.getElementById('arrowDown').classList.toggle('show', yOffset > 0);
  // FLIPPED: X positive = content moves LEFT on paper
  document.getElementById('arrowLeft').classList.toggle('show', xOffset > 0);
  document.getElementById('arrowRight').classList.toggle('show', xOffset < 0);
  
  document.getElementById('scaleInfo').textContent = 
    `Scale: ${scale.toFixed(1)}px/mm | Label: ${labelW.toFixed(1)}×${labelH.toFixed(1)}mm`;
}

async function saveConfig(){
  const body = {
    x_offset: parseInt(document.getElementById('x_offset').value, 10),
    y_offset: parseInt(document.getElementById('y_offset').value, 10),
    label_width_mm: parseFloat(document.getElementById('label_width_mm').value),
    label_height_mm: parseFloat(document.getElementById('label_height_mm').value),
    gap_mm: parseFloat(document.getElementById('gap_mm').value)
  };
  try {
    const r = await fetch('/api/config', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(body)
    });
    const data = await r.json();
    if(r.ok) {
      setStatus('Settings saved');
      updateVisualizer();
    } else {
      setStatus('Save failed: ' + (data.error||'unknown'), true);
    }
  } catch(e) {
    setStatus('Error: ' + e.message, true);
  }
}

async function feedControl(action){
  try {
    const r = await fetch('/api/feed', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({action})
    });
    const data = await r.json();
    setStatus(r.ok ? (action === 'reset' ? 'Position reset' : 'Label fed') : 'Error');
  } catch(e) {
    setStatus('Error: ' + e.message, true);
  }
}

async function nudge(axis, mm){
  try {
    const r = await fetch('/api/nudge', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({axis, mm})
    });
    const data = await r.json();
    if(r.ok) {
      document.getElementById('x_offset').value = data.x_offset;
      document.getElementById('y_offset').value = data.y_offset;
      updateVisualizer();
      setStatus(`Nudged ${axis} by ${mm}mm → X:${data.x_offset} Y:${data.y_offset} dots`);
    } else {
      setStatus('Nudge failed: ' + (data.error||'unknown'), true);
    }
  } catch(e) {
    setStatus('Error: ' + e.message, true);
  }
}

async function printTest(kind){
  try {
    const r = await fetch('/api/print-test/' + kind, {method: 'POST'});
    setStatus(r.ok ? 'Print sent' : 'Print error');
  } catch(e) {
    setStatus('Error: ' + e.message, true);
  }
}

async function restartService(){
  if(!confirm('Restart the print service?')) return;
  try {
    const r = await fetch('/api/restart', {method: 'POST'});
    const data = await r.json();
    setStatus(r.ok && data.ok ? 'Service restarted' : ('Failed: '+(data.error||'unknown')), !r.ok || !data.ok);
  } catch(e) {
    setStatus('Error: ' + e.message, true);
  }
}

loadConfig();
</script>
</body>
</html>
"""

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