# -*- coding: utf-8 -*-
"""Independent minimal DXF reader: validates structure and re-renders entities."""
import sys
import numpy as np
import cv2


def parse(path):
    with open(path, "r", encoding="ascii", errors="strict") as fh:
        raw = fh.read()
    lines = raw.replace("\r\n", "\n").split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    if len(lines) % 2 != 0:
        raise ValueError("odd number of tag lines: file is malformed")
    tags = []
    for i in range(0, len(lines), 2):
        code_s = lines[i].strip()
        if not code_s.lstrip("-").isdigit():
            raise ValueError("group code %r is not an integer at line %d" % (code_s, i + 1))
        tags.append((int(code_s), lines[i + 1]))
    return tags


def sections(tags):
    out = {}
    i = 0
    while i < len(tags):
        if tags[i] == (0, "SECTION"):
            name = tags[i + 1][1]
            j = i + 1
            body = []
            while j < len(tags) and tags[j] != (0, "ENDSEC"):
                body.append(tags[j])
                j += 1
            out.setdefault(name, []).extend(body)
            i = j
        else:
            i += 1
    return out


def main(path):
    tags = parse(path)
    secs = sections(tags)
    print("sections:", ", ".join(sorted(secs)))

    hv = {}
    i = 0
    hdr = secs.get("HEADER", [])
    while i < len(hdr):
        if hdr[i][0] == 9:
            name = hdr[i][1]
            vals = []
            i += 1
            while i < len(hdr) and hdr[i][0] != 9:
                vals.append(hdr[i])
                i += 1
            hv[name] = vals
        else:
            i += 1
    for k in ("$ACADVER", "$INSUNITS", "$MEASUREMENT", "$EXTMIN", "$EXTMAX"):
        if k not in hv:
            print("MISSING header var", k)
        else:
            print("  %-10s %s" % (k, [v for _, v in hv[k]]))

    ents = []
    cur = None
    for code, val in secs.get("ENTITIES", []):
        if code == 0:
            cur = {"type": val, "data": []}
            ents.append(cur)
        elif cur is not None:
            cur["data"].append((code, val))
    kinds = {}
    for e in ents:
        kinds[e["type"]] = kinds.get(e["type"], 0) + 1
    print("entities:", kinds)

    layers_in_table = set()
    tbl = secs.get("TABLES", [])
    j = 0
    while j < len(tbl):
        if tbl[j] == (0, "LAYER"):
            for c, v in tbl[j + 1: j + 8]:
                if c == 2:
                    layers_in_table.add(v)
                    break
        j += 1
    print("layer table:", sorted(layers_in_table))

    bad = []
    for e in ents:
        for c, v in e["data"]:
            if c in (8,):
                if v not in layers_in_table:
                    bad.append("entity on undeclared layer %r" % v)
    # polylines must be 66=1 ... VERTEX ... SEQEND
    in_poly = False
    vcount = 0
    for e in ents:
        t = e["type"]
        d = dict(e["data"])
        if t == "POLYLINE":
            if d.get(66) != "1":
                bad.append("POLYLINE without 66=1 flag")
            in_poly = True
            vcount = 0
        elif t == "VERTEX":
            if not in_poly:
                bad.append("VERTEX outside POLYLINE")
            vcount += 1
        elif t == "SEQEND":
            if not in_poly:
                bad.append("SEQEND without POLYLINE")
            in_poly = False
        elif in_poly and t not in ("VERTEX",):
            bad.append("entity %s inside POLYLINE block" % t)
    if in_poly:
        bad.append("unterminated POLYLINE")
    print("structure problems:", bad if bad else "none")

    # ---- render
    xs, ys = [], []

    def track(x, y):
        xs.append(x); ys.append(y)

    segs = []
    circles = []
    texts = []
    poly = None
    for e in ents:
        d = {}
        for c, v in e["data"]:
            d.setdefault(c, []).append(v)
        t = e["type"]

        def f(code, idx=0):
            return float(d[code][idx])
        if t == "LINE":
            p = ((f(10), f(20)), (f(11), f(21)))
            segs.append(p)
            track(*p[0]); track(*p[1])
        elif t == "POLYLINE":
            poly = {"pts": [], "closed": int(float(d.get(70, ["0"])[0])) & 1 == 1}
        elif t == "VERTEX" and poly is not None:
            poly["pts"].append((f(10), f(20)))
        elif t == "SEQEND" and poly is not None:
            pts = poly["pts"]
            for a, b in zip(pts[:-1], pts[1:]):
                segs.append((a, b))
            if poly["closed"] and len(pts) > 2:
                segs.append((pts[-1], pts[0]))
            for p in pts:
                track(*p)
            poly = None
        elif t == "CIRCLE":
            circles.append((f(10), f(20), f(40)))
            track(f(10) - f(40), f(20) - f(40)); track(f(10) + f(40), f(20) + f(40))
        elif t == "TEXT":
            texts.append((f(10), f(20), d[1][0]))
    xmin, xmax = min(xs), max(xs)
    ymin, ymax = min(ys), max(ys)
    print("geometry extents: x %.1f..%.1f  y %.1f..%.1f  -> %.0f x %.0f units"
          % (xmin, xmax, ymin, ymax, xmax - xmin, ymax - ymin))

    W = 1200
    sc = W / max(xmax - xmin, 1e-6)
    H = int((ymax - ymin) * sc) + 20
    canvas = np.full((H, W + 20), 255, np.uint8)

    def px(p):
        return (int(round((p[0] - xmin) * sc)) + 10, int(round(H - 10 - (p[1] - ymin) * sc)))

    for a, b in segs:
        cv2.line(canvas, px(a), px(b), 0, 2, cv2.LINE_AA)
    for cx, cy, r in circles:
        cv2.circle(canvas, px((cx, cy)), int(round(r * sc)), 0, 2, cv2.LINE_AA)
    for tx, ty, s in texts:
        cv2.putText(canvas, s, px((tx, ty)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, 0, 1, cv2.LINE_AA)
    outp = sys.argv[2] if len(sys.argv) > 2 else None
    if outp:
        cv2.imencode(".png", canvas)[1].tofile(outp)
        print("rendered:", outp)
    print("segments:", len(segs), " circles:", len(circles), " texts:", len(texts))


if __name__ == "__main__":
    main(sys.argv[1])
