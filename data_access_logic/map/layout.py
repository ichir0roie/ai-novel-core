#!/usr/bin/env python3
"""SVG(Python)と HTML(JS)で同じ決め方をする。"""
from __future__ import annotations

from data_access_logic.map.collect import MapPlace
from db.polygon import outer_ring

__all__ = ["Frame", "fit_frame", "text_width", "place_labels"]

PAD_DEG = 10
GRID_DEG = 10
MIN_SCALE = 6.0
TARGET_WIDTH = 1400.0


class Frame:
    def __init__(self, lon_min, lon_max, lat_min, lat_max, scale, left=60, top=40):
        self.lon_min, self.lon_max = lon_min, lon_max
        self.lat_min, self.lat_max = lat_min, lat_max
        self.scale, self.left, self.top = scale, left, top

    @property
    def plot_width(self) -> float:
        return (self.lon_max - self.lon_min) * self.scale

    @property
    def plot_height(self) -> float:
        return (self.lat_max - self.lat_min) * self.scale

    def x(self, lon) -> float:
        return self.left + (float(lon) - self.lon_min) * self.scale

    def y(self, lat) -> float:
        return self.top + (self.lat_max - float(lat)) * self.scale

    def grid_step(self) -> int:
        span = max(self.lon_max - self.lon_min, self.lat_max - self.lat_min)
        return 30 if span > 180 else (10 if span > 60 else 5)


def _floor(v, step):
    return int(v // step) * step


def _ceil(v, step):
    return -_floor(-v, step)


def fit_frame(points: list[MapPlace], shapes: list[MapPlace] = ()) -> Frame:
    lons = [p.lon for p in points]
    lats = [p.lat for p in points]
    for shape in shapes:
        for lon, lat in outer_ring(shape.polygon):
            lons.append(lon)
            lats.append(lat)
    if not lons:
        return Frame(-180, 180, -90, 90, MIN_SCALE / 2)
    lon_min = max(-180, _floor(min(lons) - PAD_DEG, GRID_DEG))
    lon_max = min(180, _ceil(max(lons) + PAD_DEG, GRID_DEG))
    lat_min = max(-90, _floor(min(lats) - PAD_DEG, GRID_DEG))
    lat_max = min(90, _ceil(max(lats) + PAD_DEG, GRID_DEG))
    scale = max(MIN_SCALE, TARGET_WIDTH / (lon_max - lon_min))
    return Frame(lon_min, lon_max, lat_min, lat_max, scale)


def text_width(text: str, font_px: float = 11) -> float:
    return sum(font_px if ord(ch) > 0x2E7F else font_px * 0.55 for ch in text)


_CANDIDATES = (
    ("start", 8, 4), ("end", -8, 4), ("middle", 0, -9), ("middle", 0, 15),
    ("start", 8, -8), ("start", 8, 16), ("end", -8, -8), ("end", -8, 16),
)


def _overlaps(a, b) -> bool:
    return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])


def place_labels(items: list[tuple[float, float, str]], font_px: float = 11) -> list[tuple[float, float, str]]:
    """同じ点に重なる印は呼ぶ側で `y` をずらして渡す。"""
    placed = []
    result = []
    for x, y, text in items:
        w, h = text_width(text, font_px), font_px + 2
        chosen = None
        for anchor, dx, dy in _CANDIDATES:
            lx = x + dx - (w if anchor == "end" else w / 2 if anchor == "middle" else 0)
            box = (lx, y + dy - h, lx + w, y + dy)
            if not any(_overlaps(box, other) for other in placed):
                chosen = (x + dx, y + dy, anchor, box)
                break
        if chosen is None:
            anchor, dx, dy = _CANDIDATES[0]
            chosen = (x + dx, y + dy, anchor, (x + dx, y + dy - h, x + dx + w, y + dy))
        placed.append(chosen[3])
        result.append(chosen[:3])
    return result
