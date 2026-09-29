#!/usr/bin/env python3
"""経緯度は度、距離は km、高度は m。"""
from __future__ import annotations

import math

__all__ = ["BEARINGS", "planet_radius_km", "angular_distance_deg", "distance_km",
           "bearing_deg", "bearing_name", "altitude_diff_text", "distance_text"]

BEARINGS = ("北", "北北東", "北東", "東北東", "東", "東南東", "南東", "南南東",
            "南", "南南西", "南西", "西南西", "西", "西北西", "北西", "北北西")


def planet_radius_km(area) -> float | None:
    """星の表面積(km²)から半径を出す。地球の 510,072,000 → 約 6,371 km。"""
    if area in (None, "") or float(area) <= 0:
        return None
    return math.sqrt(float(area) / (4 * math.pi))


def angular_distance_deg(lon1, lat1, lon2, lat2) -> float:
    p1, p2 = math.radians(float(lat1)), math.radians(float(lat2))
    dlon = math.radians(float(lon2) - float(lon1))
    dlat = p2 - p1
    h = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
    return math.degrees(2 * math.asin(min(1.0, math.sqrt(h))))


def distance_km(radius_km, lon1, lat1, lon2, lat2) -> float | None:
    if radius_km is None:
        return None
    return math.radians(angular_distance_deg(lon1, lat1, lon2, lat2)) * float(radius_km)


def bearing_deg(lon1, lat1, lon2, lat2) -> float:
    p1, p2 = math.radians(float(lat1)), math.radians(float(lat2))
    dlon = math.radians(float(lon2) - float(lon1))
    x = math.sin(dlon) * math.cos(p2)
    y = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dlon)
    return math.degrees(math.atan2(x, y)) % 360


def bearing_name(degrees) -> str:
    return BEARINGS[int((float(degrees) + 11.25) // 22.5) % 16]


def distance_text(km, deg) -> str:
    if km is None:
        return f"約{deg:.1f}度"
    if km < 100:
        return f"約{round(km):,} km"
    return f"約{round(km, -1):,.0f} km"


def altitude_diff_text(diff_m) -> str:
    if diff_m is None:
        return "高低差は不明"
    diff = float(diff_m)
    if abs(diff) < 1:
        return "同じ高さ"
    return f"{'上' if diff > 0 else '下'}へ {abs(diff):,.0f} m"
