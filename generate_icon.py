# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
"""Generate a futuristic NeuroShell icon programmatically."""
from PIL import Image, ImageDraw, ImageFont
import math, os

SIZE = 512
CENTER = SIZE // 2

img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
draw = ImageDraw.Draw(img)

# ── Background: dark rounded square ──
bg_color = (13, 17, 23, 255)  # #0d1117
corner_r = 80
draw.rounded_rectangle([(0, 0), (SIZE-1, SIZE-1)], radius=corner_r, fill=bg_color)

# ── Outer glow ring ──
for r in range(180, 200):
    alpha = max(0, 60 - (r - 180) * 3)
    glow_color = (57, 210, 192, alpha)  # cyan glow
    draw.ellipse([(CENTER-r, CENTER-r), (CENTER+r, CENTER+r)], outline=glow_color, width=1)

# ── Inner neural brain circle ──
brain_r = 140
# Gradient circle (cyan to purple)
for r in range(brain_r, brain_r - 3, -1):
    draw.ellipse([(CENTER-r, CENTER-r), (CENTER+r, CENTER+r)], outline=(57, 210, 192, 200), width=2)

# ── Neural network nodes ──
nodes = []
# Layer 1 (inner)
for i in range(5):
    angle = (2 * math.pi * i / 5) - math.pi / 2
    x = CENTER + int(55 * math.cos(angle))
    y = CENTER + int(55 * math.sin(angle))
    nodes.append((x, y, 0))  # layer 0

# Layer 2 (middle)
for i in range(8):
    angle = (2 * math.pi * i / 8) - math.pi / 4
    x = CENTER + int(100 * math.cos(angle))
    y = CENTER + int(100 * math.sin(angle))
    nodes.append((x, y, 1))  # layer 1

# Layer 3 (outer)
for i in range(10):
    angle = (2 * math.pi * i / 10)
    x = CENTER + int(135 * math.cos(angle))
    y = CENTER + int(135 * math.sin(angle))
    nodes.append((x, y, 2))  # layer 2

# ── Draw connections ──
for i, (x1, y1, l1) in enumerate(nodes):
    for j, (x2, y2, l2) in enumerate(nodes):
        if l2 == l1 + 1:
            dist = math.sqrt((x2-x1)**2 + (y2-y1)**2)
            if dist < 130:
                # Gradient from cyan to purple
                t = j / len(nodes)
                r = int(57 + (188 - 57) * t)
                g = int(210 + (140 - 210) * t)
                b = int(192 + (255 - 192) * t)
                draw.line([(x1, y1), (x2, y2)], fill=(r, g, b, 80), width=1)

# ── Draw nodes ──
for x, y, layer in nodes:
    if layer == 0:
        color = (57, 210, 192, 255)  # cyan
        node_r = 7
    elif layer == 1:
        color = (130, 180, 220, 255)  # blue-cyan
        node_r = 5
    else:
        color = (188, 140, 255, 255)  # purple
        node_r = 4
    
    # Glow
    for gr in range(node_r + 6, node_r, -1):
        alpha = max(0, 40 - (gr - node_r) * 8)
        draw.ellipse([(x-gr, y-gr), (x+gr, y+gr)], fill=(color[0], color[1], color[2], alpha))
    # Node
    draw.ellipse([(x-node_r, y-node_r), (x+node_r, y+node_r)], fill=color)

# ── Central brain symbol ──
# Terminal cursor ">" symbol
cx, cy = CENTER, CENTER
# Draw a stylized ">" cursor
points_gt = [(cx-18, cy-25), (cx+18, cy), (cx-18, cy+25)]
draw.polygon(points_gt, fill=(57, 210, 192, 220))

# ── Add subtle "N" watermark in bottom-right ──
try:
    font = ImageFont.truetype("arial.ttf", 48)
except:
    font = ImageFont.load_default()

# ── Save ──
assets_dir = os.path.join(os.path.dirname(__file__), "assets")
os.makedirs(assets_dir, exist_ok=True)

# Save PNG
png_path = os.path.join(assets_dir, "logo.png")
img.save(png_path, "PNG")
print(f"✅ Saved: {png_path}")

# Save ICO (multiple sizes for Windows)
ico_path = os.path.join(assets_dir, "icon.ico")
sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
icons = [img.resize(s, Image.LANCZOS) for s in sizes]
icons[0].save(ico_path, format="ICO", sizes=[(s[0], s[1]) for s in sizes], append_images=icons[1:])
print(f"✅ Saved: {ico_path}")
print("🎨 NeuroShell icon generated!")
