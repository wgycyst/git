# -*- coding: utf-8 -*-
"""Hand-drawn sketch (photo or scan) -> DXF line work for AutoCAD 2024.

Pipeline
  1. optional perspective correction (sheet corners given, or auto-detected)
  2. illumination normalisation (kills phone-photo shadows / uneven light)
  3. Otsu binarisation with polarity auto-detect
  4. despeckle small blobs
  5. skeletonise to 1-px centre lines
  6. trace the pixel graph into open / closed strokes
  7. Douglas-Peucker simplification, optional ortho snap (walls square)
  8. scale to real units from one reference dimension
  9. write an R12 DXF (dxfout.py) plus a preview PNG for visual checking

Requires numpy + opencv-python; scikit-image is used when available.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys

import numpy as np
import cv2

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from dxfout import DXF  # noqa: E402

NB8 = ((-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1))
NBC = np.array([[1, 1, 1], [1, 0, 1], [1, 1, 1]], dtype=np.uint8)


# --------------------------------------------------------------------- io
def imread(path):
    data = np.fromfile(path, dtype=np.uint8)
    img = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if img is None:
        raise SystemExit("cannot decode image: %s" % path)
    return img


def imwrite(path, img):
    ext = os.path.splitext(path)[1].lower() or ".png"
    ok, buf = cv2.imencode(ext, img)
    if not ok:
        raise SystemExit("cannot encode image: %s" % path)
    buf.tofile(path)


# ------------------------------------------------------- perspective fix
def order_quad(pts):
    pts = np.array(pts, dtype=np.float32).reshape(4, 2)
    s = pts.sum(axis=1)
    d = (pts[:, 1] - pts[:, 0])
    return np.array([pts[np.argmin(s)], pts[np.argmin(d)],
                     pts[np.argmax(s)], pts[np.argmax(d)]], dtype=np.float32)


def warp_quad(img, quad):
    tl, tr, br, bl = order_quad(quad)
    w = int(max(np.linalg.norm(tr - tl), np.linalg.norm(br - bl)))
    h = int(max(np.linalg.norm(bl - tl), np.linalg.norm(br - tr)))
    w = max(w, 32)
    h = max(h, 32)
    dst = np.array([[0, 0], [w - 1, 0], [w - 1, h - 1], [0, h - 1]], dtype=np.float32)
    m = cv2.getPerspectiveTransform(np.array([tl, tr, br, bl], dtype=np.float32), dst)
    return cv2.warpPerspective(img, m, (w, h), flags=cv2.INTER_CUBIC,
                               borderMode=cv2.BORDER_REPLICATE)


def detect_paper(gray):
    """Largest 4-corner contour that covers a good share of the frame."""
    h, w = gray.shape
    scale = 1000.0 / float(max(h, w))
    if scale < 1.0:
        small = cv2.resize(gray, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    else:
        small = gray
        scale = 1.0
    blur = cv2.GaussianBlur(small, (5, 5), 0)
    edges = cv2.Canny(blur, 40, 120)
    edges = cv2.dilate(edges, np.ones((3, 3), np.uint8), iterations=2)
    cnts = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[0]
    area_img = float(small.shape[0] * small.shape[1])
    found = None
    for c in sorted(cnts, key=cv2.contourArea, reverse=True)[:8]:
        if cv2.contourArea(c) < 0.25 * area_img:
            continue
        peri = cv2.arcLength(c, True)
        for eps in (0.02, 0.03, 0.05, 0.08):
            ap = cv2.approxPolyDP(c, eps * peri, True)
            if len(ap) == 4:
                found = ap.reshape(4, 2).astype(np.float32)
                break
        if found is not None:
            break
    if found is None:
        return None
    return found / scale


# ----------------------------------------------------------- binarisation
def normalize_illumination(gray):
    sigma = max(gray.shape) / 25.0
    bg = cv2.GaussianBlur(gray, (0, 0), sigma)
    bg = np.maximum(bg, 1)
    return cv2.divide(gray, bg, scale=255)


def binarize(gray, invert="auto"):
    norm = normalize_illumination(gray)
    norm = cv2.medianBlur(norm, 3)
    _, bw = cv2.threshold(norm, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    ink = bw < 128
    if invert == "yes":
        ink = ~ink
    elif invert == "auto" and ink.mean() > 0.5:
        ink = ~ink
    return ink


def despeckle(ink, min_area):
    n, lab, stats, _ = cv2.connectedComponentsWithStats(ink.astype(np.uint8), connectivity=8)
    if n <= 1:
        return ink
    keep = np.zeros(n, dtype=bool)
    keep[1:] = stats[1:, cv2.CC_STAT_AREA] >= min_area
    return keep[lab]


# ------------------------------------------------------------ skeleton
def zhang_suen(img):
    """Vectorised Zhang-Suen thinning, used when skimage / ximgproc is absent."""
    img = (img > 0).astype(np.uint8)
    changed = True
    while changed:
        changed = False
        for step in (0, 1):
            p = np.pad(img, 1)
            p2 = p[0:-2, 1:-1]; p3 = p[0:-2, 2:]; p4 = p[1:-1, 2:]
            p5 = p[2:, 2:]; p6 = p[2:, 1:-1]; p7 = p[2:, 0:-2]
            p8 = p[1:-1, 0:-2]; p9 = p[0:-2, 0:-2]
            b = p2 + p3 + p4 + p5 + p6 + p7 + p8 + p9
            ring = [p2, p3, p4, p5, p6, p7, p8, p9, p2]
            a = np.zeros_like(b)
            for i in range(8):
                a = a + ((ring[i] == 0) & (ring[i + 1] == 1)).astype(np.uint8)
            if step == 0:
                cond = ((b >= 2) & (b <= 6) & (a == 1) &
                        ((p2 * p4 * p6) == 0) & ((p4 * p6 * p8) == 0))
            else:
                cond = ((b >= 2) & (b <= 6) & (a == 1) &
                        ((p2 * p4 * p8) == 0) & ((p2 * p6 * p8) == 0))
            rm = (img == 1) & cond
            if rm.any():
                img = (img & (~rm).astype(np.uint8)).astype(np.uint8)
                changed = True
    return img.astype(bool)


def skeletonize(ink):
    try:
        from skimage.morphology import skeletonize as _sk
        return _sk(ink)
    except Exception:
        pass
    try:
        thin = cv2.ximgproc.thinning((ink.astype(np.uint8) * 255))
        return thin > 0
    except Exception:
        pass
    return zhang_suen(ink)


# -------------------------------------------------------------- tracing
def trace_paths(sk):
    """Split the 1-px skeleton into pixel paths between nodes / dead ends."""
    h, w = sk.shape
    if not sk.any():
        return []
    deg = cv2.filter2D(sk.astype(np.uint8), -1, NBC, borderType=cv2.BORDER_CONSTANT)
    nbrs = {}
    for r, c in np.argwhere(sk):
        r = int(r); c = int(c)
        lst = []
        for dr, dc in NB8:
            rr = r + dr; cc = c + dc
            if 0 <= rr < h and 0 <= cc < w and sk[rr, cc]:
                lst.append(rr * w + cc)
        nbrs[r * w + c] = lst

    visited = set()
    paths = []

    def ekey(a, b):
        return (a, b) if a < b else (b, a)

    def walk(start, first):
        path = [start, first]
        visited.add(ekey(start, first))
        prev, cur = start, first
        while deg[cur // w, cur % w] == 2:
            nxt = -1
            for cand in nbrs[cur]:
                if cand != prev and ekey(cur, cand) not in visited:
                    nxt = cand
                    break
            if nxt < 0:
                break
            visited.add(ekey(cur, nxt))
            path.append(nxt)
            prev, cur = cur, nxt
        return path

    for key in list(nbrs):
        if deg[key // w, key % w] == 2:
            continue
        for n in nbrs[key]:
            if ekey(key, n) not in visited:
                paths.append(walk(key, n))
    for key in nbrs:
        if deg[key // w, key % w] != 2:
            continue
        for n in nbrs[key]:
            if ekey(key, n) not in visited:
                paths.append(walk(key, n))
    return paths


def path_xy(path, w):
    return np.array([[p % w, p // w] for p in path], dtype=np.float32)


def simplify(pts, eps):
    if eps <= 0 or len(pts) < 3:
        return pts
    ap = cv2.approxPolyDP(pts.reshape(-1, 1, 2), float(eps), False)
    return ap.reshape(-1, 2)


def dedupe(pts):
    if len(pts) < 2:
        return pts
    keep = [0]
    for i in range(1, len(pts)):
        if abs(pts[i, 0] - pts[keep[-1], 0]) > 1e-9 or abs(pts[i, 1] - pts[keep[-1], 1]) > 1e-9:
            keep.append(i)
    return pts[keep]


def arc_len(pts):
    if len(pts) < 2:
        return 0.0
    d = np.diff(pts, axis=0)
    return float(np.sum(np.hypot(d[:, 0], d[:, 1])))


def ortho_snap(pts, tol_deg):
    if tol_deg <= 0 or len(pts) < 2:
        return pts
    pts = pts.copy()
    for i in range(len(pts) - 1):
        p = pts[i]; q = pts[i + 1]
        dx = float(q[0] - p[0]); dy = float(q[1] - p[1])
        if dx == 0.0 and dy == 0.0:
            continue
        ang = math.degrees(math.atan2(dy, dx)) % 180.0
        if min(ang, 180.0 - ang) <= tol_deg:
            pts[i + 1] = (q[0], p[1])
        elif abs(ang - 90.0) <= tol_deg:
            pts[i + 1] = (p[0], q[1])
    return pts


# ---------------------------------------------------------------- helpers
def parse_points(text, expected):
    vals = [float(v) for v in text.replace(";", ",").split(",") if v.strip() != ""]
    if len(vals) != expected * 2:
        raise SystemExit("expected %d points as x,y,x,y,... - got %d numbers" % (expected, len(vals)))
    return [(vals[i], vals[i + 1]) for i in range(0, len(vals), 2)]


def draw_grid(img, step, color=(0, 170, 255)):
    h, w = img.shape[:2]
    for x in range(0, w, step):
        cv2.line(img, (x, 0), (x, h), color, 1, cv2.LINE_AA)
        cv2.putText(img, str(x), (x + 3, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1, cv2.LINE_AA)
    for y in range(0, h, step):
        cv2.line(img, (0, y), (w, y), color, 1, cv2.LINE_AA)
        cv2.putText(img, str(y), (3, y + 16), cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1, cv2.LINE_AA)
    return img


# ------------------------------------------------------------------ main
def run(args):
    img = imread(args.input)
    oh, ow = img.shape[:2]
    notes = []
    warped = False
    if args.corners:
        img = warp_quad(img, parse_points(args.corners, 4))
        warped = True
        notes.append("perspective corrected from 4 given corners")
    elif args.auto_crop:
        quad = detect_paper(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY))
        if quad is None:
            notes.append("auto-crop: sheet not detected, image used as-is")
        else:
            img = warp_quad(img, quad)
            warped = True
            notes.append("auto-crop: sheet detected and rectified")

    # a rectified sheet keeps a dark rim from the paper edge: cut it off
    trim = args.trim if args.trim >= 0 else (8 if warped else 0)
    if trim > 0 and 2 * trim < min(img.shape[:2]):
        img = img[trim: img.shape[0] - trim, trim: img.shape[1] - trim]
        notes.append("trimmed %d px sheet rim" % trim)

    h, w = img.shape[:2]
    if args.max_dim and max(h, w) > args.max_dim:
        f = args.max_dim / float(max(h, w))
        work = cv2.resize(img, (max(1, int(round(w * f))), max(1, int(round(h * f)))),
                          interpolation=cv2.INTER_AREA)
    else:
        work = img
    wh, ww = work.shape[:2]

    gray = cv2.cvtColor(work, cv2.COLOR_BGR2GRAY)
    ink = binarize(gray, args.invert)
    ink_ratio = float(ink.mean())
    ink = despeckle(ink, args.min_area)
    sk = skeletonize(ink)
    raw = trace_paths(sk)

    strokes = []
    for p in raw:
        pts = simplify(path_xy(p, ww), args.simplify)
        pts = dedupe(pts)
        if len(pts) < 2 or arc_len(pts) < args.min_len:
            continue
        if args.ortho > 0:
            pts = ortho_snap(pts, args.ortho)
        closed = False
        if len(pts) >= 4 and math.hypot(float(pts[0, 0] - pts[-1, 0]),
                                        float(pts[0, 1] - pts[-1, 1])) <= args.close_tol:
            pts = pts[:-1]
            closed = arc_len(np.vstack([pts, pts[:1]])) > 0
        strokes.append((pts, bool(closed)))

    mm_per_px = 1.0
    scale_src = "none (1 drawing unit = 1 working pixel)"
    if args.ref and args.ref_mm:
        (x1, y1), (x2, y2) = parse_points(args.ref, 2)
        d = math.hypot(x2 - x1, y2 - y1)
        if d <= 1e-9:
            raise SystemExit("--ref points coincide")
        mm_per_px = float(args.ref_mm) / d
        scale_src = "reference %.1f mm over %.1f px" % (args.ref_mm, d)
    elif args.width_mm:
        mm_per_px = float(args.width_mm) / float(ww)
        scale_src = "image width %.0f mm over %d px" % (args.width_mm, ww)

    dxf = DXF()
    dxf.layer("SKETCH", 3)
    n_ent = 0
    n_vert = 0
    total_len = 0.0
    for pts, closed in strokes:
        xy = [(float(p[0]) * mm_per_px, (wh - float(p[1])) * mm_per_px) for p in pts]
        n_vert += len(xy)
        segs = list(zip(xy[:-1], xy[1:]))
        if closed:
            segs.append((xy[-1], xy[0]))
        for a, b in segs:
            total_len += math.hypot(b[0] - a[0], b[1] - a[1])
        if args.mode == "line":
            for a, b in segs:
                dxf.line(a[0], a[1], b[0], b[1], "SKETCH")
                n_ent += 1
        else:
            dxf.polyline(xy, "SKETCH", closed=closed)
            n_ent += 1

    if args.frame:
        dxf.layer("SKETCH_FRAME", 8)
        fx = [0.0, ww * mm_per_px]
        fy = [0.0, wh * mm_per_px]
        pts = [(fx[0], fy[0]), (fx[1], fy[0]), (fx[1], fy[1]), (fx[0], fy[1])]
        dxf.polyline(pts, "SKETCH_FRAME", closed=True)
        n_ent += 1

    out = args.out or (os.path.splitext(args.input)[0] + ".dxf")
    dxf.save(out)

    preview = args.preview
    if preview is None and not args.no_preview:
        preview = os.path.splitext(out)[0] + "_preview.png"
    if preview:
        vis = work.copy()
        if args.grid:
            draw_grid(vis, args.grid_step)
        for pts, closed in strokes:
            seq = np.round(pts).astype(np.int32).reshape(-1, 1, 2)
            cv2.polylines(vis, [seq], closed, (0, 0, 255), 2, cv2.LINE_AA)
            for p in pts:
                cv2.circle(vis, (int(round(p[0])), int(round(p[1]))), 2, (0, 200, 0), -1, cv2.LINE_AA)
        imwrite(preview, vis)

    if args.json:
        payload = {
            "input": os.path.abspath(args.input),
            "working_size": [ww, wh],
            "mm_per_px": mm_per_px,
            "scale_source": scale_src,
            "strokes": [{"closed": c, "points": [[float(x), float(y)] for x, y in p]}
                        for p, c in strokes],
        }
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=1)

    print("input      : %s  (%dx%d)" % (args.input, ow, oh))
    if (w, h) != (ow, oh):
        print("prepared   : %dx%d  (after rectify/trim; preview and --ref use this frame)" % (w, h))
    print("working    : %dx%d  (analysis resolution, preview uses the same frame)" % (ww, wh))
    print("ink ratio  : %.2f%%   strokes kept: %d   raw paths: %d" % (ink_ratio * 100.0, len(strokes), len(raw)))
    print("scale      : 1 px = %.4f unit  [%s]" % (mm_per_px, scale_src))
    print("total drawn: %.1f units" % total_len)
    print("dxf        : %s  (%d entities, %d vertices, layer SKETCH)" % (out, n_ent, n_vert))
    if preview:
        print("preview    : %s" % preview)
    for note in notes:
        print("note       : %s" % note)
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="Hand-drawn sketch -> DXF for AutoCAD.")
    ap.add_argument("input", nargs="?", help="photo or scan of the hand-drawn sketch")
    ap.add_argument("-o", "--out", help="output .dxf (default: input name with .dxf)")
    ap.add_argument("--mode", choices=["trace", "line"], default="trace",
                    help="trace = polylines (default), line = one LINE per straight segment")
    ap.add_argument("--simplify", type=float, default=2.5,
                    help="Douglas-Peucker tolerance in working pixels (default 2.5)")
    ap.add_argument("--min-len", type=float, default=25.0,
                    help="drop strokes shorter than this, working px (default 25)")
    ap.add_argument("--min-area", type=float, default=12.0,
                    help="despeckle: drop blobs smaller than this, px (default 12)")
    ap.add_argument("--ortho", type=float, default=0.0,
                    help="snap segments within N degrees of horizontal/vertical (default 0 = off, try 2)")
    ap.add_argument("--close-tol", type=float, default=3.0,
                    help="endpoint distance that makes a stroke closed, px (default 3)")
    ap.add_argument("--max-dim", type=int, default=2200,
                    help="downscale so the longest side is at most this (default 2200, 0 = keep)")
    ap.add_argument("--invert", choices=["auto", "yes", "no"], default="auto",
                    help="white ink on dark background: yes (default auto)")
    ap.add_argument("--auto-crop", action="store_true", help="detect and rectify the sheet")
    ap.add_argument("--trim", type=int, default=-1,
                    help="cut N px of sheet rim after rectifying (default: 8 when rectified, else 0)")
    ap.add_argument("--corners", help="paper corners in the ORIGINAL photo: x1,y1,x2,y2,x3,y3,x4,y4")
    ap.add_argument("--ref", help="two reference points in WORKING px: x1,y1,x2,y2")
    ap.add_argument("--ref-mm", type=float, help="real length of the --ref distance, mm")
    ap.add_argument("--width-mm", type=float, help="alternative scale: real width of the whole sheet, mm")
    ap.add_argument("--frame", action="store_true", help="also draw the sheet frame on layer SKETCH_FRAME")
    ap.add_argument("--grid", action="store_true", help="draw a labelled coordinate grid on the preview")
    ap.add_argument("--grid-step", type=int, default=100, help="grid spacing in working px (default 100)")
    ap.add_argument("--preview", help="preview PNG path")
    ap.add_argument("--no-preview", action="store_true")
    ap.add_argument("--json", help="also dump vertex data as JSON")
    args = ap.parse_args(argv)

    if not args.input:
        ap.print_help()
        return 2
    return run(args)


if __name__ == "__main__":
    sys.exit(main())

