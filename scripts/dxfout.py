# -*- coding: utf-8 -*-
"""Minimal DXF R12 (AC1009) ASCII writer, standard library only.

Why R12: it is the most tolerant DXF dialect (no handles, no object IDs, no
dictionaries) and AutoCAD 2024 opens it natively.  Coordinates are written in
drawing units; we use millimetres (INSUNITS = 4).
"""


def _num(v):
    v = float(v)
    if v.is_integer():
        return str(int(v))
    return "{:.6f}".format(v).rstrip("0").rstrip(".")


class DXF(object):
    def __init__(self, insunits=4, measurement=1):
        self.insunits = insunits
        self.measurement = measurement
        self._layers = {"0": 7}
        self._entities = []          # list of [(code, value), ...]
        self._min = [float("inf"), float("inf")]
        self._max = [float("-inf"), float("-inf")]

    # ---------------------------------------------------------------- layers
    def layer(self, name, color=7):
        self._layers[name] = int(color)
        return name

    # ------------------------------------------------------------- internals
    def _track(self, x, y):
        if x < self._min[0]:
            self._min[0] = x
        if y < self._min[1]:
            self._min[1] = y
        if x > self._max[0]:
            self._max[0] = x
        if y > self._max[1]:
            self._max[1] = y

    def _add(self, tags):
        self._entities.append(tags)

    # ------------------------------------------------------------ primitives
    def line(self, x1, y1, x2, y2, layer="0"):
        self.layer(layer)
        self._track(x1, y1)
        self._track(x2, y2)
        self._add([(0, "LINE"), (8, layer),
                   (10, _num(x1)), (20, _num(y1)), (30, "0.0"),
                   (11, _num(x2)), (21, _num(y2)), (31, "0.0")])

    def polyline(self, points, layer="0", closed=False):
        pts = [(float(x), float(y)) for x, y in points]
        if len(pts) < 2:
            return
        self.layer(layer)
        for x, y in pts:
            self._track(x, y)
        tags = [(0, "POLYLINE"), (8, layer), (66, 1), (70, 1 if closed else 0),
                (10, "0.0"), (20, "0.0"), (30, "0.0")]
        for x, y in pts:
            tags.extend([(0, "VERTEX"), (8, layer),
                         (10, _num(x)), (20, _num(y)), (30, "0.0")])
        tags.append((0, "SEQEND"))
        tags.append((8, layer))
        self._add(tags)

    def point(self, x, y, layer="0"):
        self.layer(layer)
        self._track(x, y)
        self._add([(0, "POINT"), (8, layer),
                   (10, _num(x)), (20, _num(y)), (30, "0.0")])

    def circle(self, x, y, r, layer="0"):
        self.layer(layer)
        self._track(x - r, y - r)
        self._track(x + r, y + r)
        self._add([(0, "CIRCLE"), (8, layer), (10, _num(x)), (20, _num(y)),
                   (30, "0.0"), (40, _num(r))])

    def text(self, x, y, height, value, layer="0", style="STANDARD"):
        self.layer(layer)
        self._track(x, y)
        self._add([(0, "TEXT"), (8, layer),
                   (10, _num(x)), (20, _num(y)), (30, "0.0"),
                   (40, _num(height)), (1, str(value)), (7, style)])

    # ---------------------------------------------------------------- output
    def entity_count(self):
        return len(self._entities)

    def render(self):
        out = []

        def t(code, value):
            out.append(str(code))
            out.append(str(value))

        if self._min[0] == float("inf"):
            xmin, ymin, xmax, ymax = 0.0, 0.0, 100.0, 100.0
        else:
            xmin, ymin = self._min
            xmax, ymax = self._max
        cw = max(xmax - xmin, 1e-6)
        ch = max(ymax - ymin, 1e-6)

        # ---- HEADER
        t(0, "SECTION")
        t(2, "HEADER")
        t(9, "$ACADVER")
        t(1, "AC1009")
        t(9, "$INSBASE")
        t(10, "0.0"); t(20, "0.0"); t(30, "0.0")
        t(9, "$EXTMIN")
        t(10, _num(xmin)); t(20, _num(ymin)); t(30, "0.0")
        t(9, "$EXTMAX")
        t(10, _num(xmax)); t(20, _num(ymax)); t(30, "0.0")
        t(9, "$LIMMIN")
        t(10, _num(xmin)); t(20, _num(ymin))
        t(9, "$LIMMAX")
        t(10, _num(xmax)); t(20, _num(ymax))
        t(9, "$LTSCALE")
        t(40, "1.0")
        t(9, "$INSUNITS")
        t(70, self.insunits)
        t(9, "$MEASUREMENT")
        t(70, self.measurement)
        t(0, "ENDSEC")

        # ---- TABLES
        t(0, "SECTION")
        t(2, "TABLES")

        t(0, "TABLE"); t(2, "VPORT"); t(70, 1)
        t(0, "VPORT"); t(2, "*ACTIVE"); t(70, 0)
        t(10, "0.0"); t(20, "0.0")
        t(11, "1.0"); t(21, "1.0")
        t(12, _num((xmin + xmax) / 2.0)); t(22, _num((ymin + ymax) / 2.0))
        t(13, "0.0"); t(23, "0.0")
        t(14, "10.0"); t(24, "10.0")
        t(15, "10.0"); t(25, "10.0")
        t(16, "0.0"); t(26, "0.0"); t(36, "1.0")
        t(17, "0.0"); t(27, "0.0"); t(37, "0.0")
        t(40, _num(ch * 1.1))
        t(41, _num(cw / ch))
        t(42, "50.0"); t(43, "0.0"); t(44, "0.0")
        t(50, "0.0"); t(51, "0.0")
        t(71, 0); t(72, 100); t(73, 1); t(74, 3); t(75, 0)
        t(76, 0); t(77, 0); t(78, 0)
        t(0, "ENDTAB")

        t(0, "TABLE"); t(2, "LTYPE"); t(70, 1)
        t(0, "LTYPE"); t(2, "CONTINUOUS"); t(70, 64)
        t(3, "Solid line"); t(72, 65); t(73, 0); t(40, "0.0")
        t(0, "ENDTAB")

        t(0, "TABLE"); t(2, "LAYER"); t(70, len(self._layers))
        for name in sorted(self._layers):
            t(0, "LAYER"); t(2, name); t(70, 0); t(62, self._layers[name])
            t(6, "CONTINUOUS")
        t(0, "ENDTAB")

        t(0, "TABLE"); t(2, "STYLE"); t(70, 1)
        t(0, "STYLE"); t(2, "STANDARD"); t(70, 0)
        t(40, "0.0"); t(41, "1.0"); t(50, "0.0")
        t(71, 0); t(42, "2.5"); t(3, "txt"); t(4, "")
        t(0, "ENDTAB")

        t(0, "TABLE"); t(2, "VIEW"); t(70, 0)
        t(0, "ENDTAB")
        t(0, "TABLE"); t(2, "UCS"); t(70, 0)
        t(0, "ENDTAB")
        t(0, "TABLE"); t(2, "APPID"); t(70, 1)
        t(0, "APPID"); t(2, "ACAD"); t(70, 0)
        t(0, "ENDTAB")

        t(0, "ENDSEC")

        # ---- ENTITIES
        t(0, "SECTION")
        t(2, "ENTITIES")
        for ent in self._entities:
            for code, value in ent:
                t(code, value)
        t(0, "ENDSEC")

        t(0, "EOF")
        return "\r\n".join(out) + "\r\n"

    def save(self, path):
        data = self.render()
        with open(path, "w", encoding="ascii", newline="") as fh:
            fh.write(data)
        return path
