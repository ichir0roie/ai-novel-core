#!/usr/bin/env python3
"""地図で場所を色分けする区分。SVG(Python)と HTML(JS)で同じものを使う。"""
from __future__ import annotations

__all__ = ["CATEGORIES", "CATEGORY_COLORS", "SHAPE_OPACITY", "category_of"]

CATEGORIES = ("大陸", "国", "都市", "自然")

CATEGORY_COLORS = {
    "大陸": "#8a6d3b",
    "国": "#2471a3",
    "都市": "#c0392b",
    "自然": "#1e8449",
}

# 輪郭の塗りの濃さ。大きい面ほど薄くして、上に重なる小さい面を見せる
SHAPE_OPACITY = {"大陸": 0.10, "国": 0.18, "都市": 0.3, "自然": 0.3}

# 地下・妖精郷・天上の「世界」は大陸と並ぶ一段なので、大陸と同じ区分にする
_CONTINENT_KINDS = {"大陸", "世界"}
_COUNTRY_KINDS = {"国"}
_CITY_KINDS = {"都市", "町", "村"}


def category_of(kind: str | None) -> str:
    if kind in _CONTINENT_KINDS:
        return "大陸"
    if kind in _COUNTRY_KINDS:
        return "国"
    if kind in _CITY_KINDS:
        return "都市"
    return "自然"
