# -*- coding: utf-8 -*-
"""Build a synthetic 'phone photo of a hand-drawn sketch' for pipeline testing."""
import os
import numpy as np
import cv2

rng = np.random.default_rng(7)
W, H = 1100, 800          # paper (drawing) area
MARGIN = 90               # blank paper margin around the drawing
PW, PH = W + 2 * MARGIN, H + 2 * MARGIN


def wobbly(p0, p1, amp=1.8, step=14.0):
    p0 = np.array(p0, float); p1 = np.array(p1, float)
    L = float(np.linalg.norm(p1 - p0))
    n = max(4, int(L / step))
    t = np.linspace(0, 1, n)[:, None]
    pts = (1 - t) * p0 + t * p1
    pts = pts + rng.normal(0, amp, pts.shape)
    return np.round(pts).astype(np.int32)


def stroke(img, p0, p1, th=3):
    c = wobbly(p0, p1)
    cv2.polylines(img, [c], False, 0, th, cv2.LINE_AA)
    cv2.polylines(img, [c + rng.normal(0, 0.8, c.shape).astype(np.int32)], False, 0, max(1, th - 2), cv2.LINE_AA)


def chain(img, pts, th=3):
    for a, b in zip(pts[:-1], pts[1:]):
        stroke(img, a, b, th)


paper = np.full((PH, PW), 252, np.uint8)
o = np.array([MARGIN, MARGIN])
room = [o + [60, 30], o + [1040, 30], o + [1040, 700], o + [60, 700], o + [60, 30]]
chain(paper, room, 3)

# partition wall with a door opening
chain(paper, [o + [560, 30], o + [560, 300]], 3)
chain(paper, [o + [560, 470], o + [560, 700]], 3)
cv2.ellipse(paper, tuple(o + [560, 300]), (170, 170), 0, 0, 90, 0, 2, cv2.LINE_AA)

# column (circle) + cross
c = tuple(o + [850, 250])
cv2.circle(paper, c, 62, 0, 3, cv2.LINE_AA)
stroke(paper, (c[0] - 62, c[1]), (c[0] + 62, c[1]), 2)
stroke(paper, (c[0], c[1] - 62), (c[0], c[1] + 62), 2)

# dimension line above the top wall
dim_y = o[1] - 45
stroke(paper, (o[0] + 60, dim_y), (o[0] + 1040, dim_y), 2)
for x in (o[0] + 60, o[0] + 1040):
    stroke(paper, (x, dim_y - 14), (x, dim_y + 14), 2)
stroke(paper, (o[0] + 60, dim_y), (o[0] + 60, o[1] + 30), 1)
stroke(paper, (o[0] + 1040, dim_y), (o[0] + 1040, o[1] + 30), 1)

# a table inside the room
chain(paper, [o + [700, 430], o + [990, 430], o + [990, 640], o + [700, 640], o + [700, 430]], 2)

# a few hatch marks on the left wall
for k in range(6):
    y = o[1] + 420 + k * 42
    stroke(paper, (o[0] + 30, y), (o[0] + 90, y + 30), 1)

# rough handwriting marks (labels)
for k, (lx, ly) in enumerate([(230, 350), (620, 620), (760, 200), (300, 640)]):
    for s in range(3):
        stroke(paper, (o[0] + lx + s * 26, o[1] + ly), (o[0] + lx + 18 + s * 26, o[1] + ly + 28), 2)

# ---- simulate the photo: tilt, perspective, light falloff, noise
M = cv2.getRotationMatrix2D((PW / 2, PH / 2), 3.0, 1.0)
photo = cv2.warpAffine(paper, M, (PW, PH), borderValue=250)

src = np.float32([[0, 0], [PW - 1, 0], [PW - 1, PH - 1], [0, PH - 1]])
dst = np.float32([[62, 70], [PW - 34, 30], [PW - 70, PH - 58], [26, PH - 22]])
M2 = cv2.getPerspectiveTransform(src, dst)
paper_area = cv2.warpPerspective(photo, M2, (PW, PH), borderValue=250)
mask = cv2.warpPerspective(np.full((PH, PW), 255, np.uint8), M2, (PW, PH), borderValue=0)

desk = np.full((PH, PW), 70, np.uint8)
desk[mask > 40] = paper_area[mask > 40]

yy, xx = np.mgrid[0:PH, 0:PW].astype(np.float32)
grad = 1.06 - 0.34 * (xx / PW) - 0.20 * (yy / PH)
img = np.clip(desk.astype(np.float32) * grad, 0, 255)
img = img + rng.normal(0, 6.0, img.shape)
img = cv2.GaussianBlur(img.astype(np.float32), (3, 3), 0.7)
out = cv2.cvtColor(np.clip(img, 0, 255).astype(np.uint8), cv2.COLOR_GRAY2BGR)

import argparse, pathlib
ap = argparse.ArgumentParser(description="generate a synthetic hand-sketch photo for testing")
ap.add_argument("-o", "--out", default=str(pathlib.Path(__file__).resolve().parent),
                help="output directory (default: this folder)")
args = ap.parse_args()
dst_dir = args.out
os.makedirs(dst_dir, exist_ok=True)
path = os.path.join(dst_dir, "hand_sketch_sample.jpg")
cv2.imencode(".jpg", out, [int(cv2.IMWRITE_JPEG_QUALITY), 88])[1].tofile(path)
print("wrote", path, out.shape)

# ground truth corners of the sheet, in photo pixel coordinates
print("sheet corners TL,TR,BR,BL:", [list(map(int, p)) for p in dst])
