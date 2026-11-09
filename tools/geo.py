# -*- coding: utf-8 -*-
"""Location, coordinate and geo tools."""

from __future__ import annotations

import json
import math
import re

from .common import ok, parse_float, split_pipe, to_ascii_digits
from .meta import make_tool
from .model import Input, Output, Tool, ToolError

TOOLS: list[Tool] = []


def _register(*tools: Tool) -> None:
    TOOLS.extend(tools)


# --------------------------------------------------------------------------
# Coordinates
# --------------------------------------------------------------------------

def _dec_to_dms(value: float, is_lat: bool) -> str:
    direction = ("N" if value >= 0 else "S") if is_lat else ("E" if value >= 0 else "W")
    absolute = abs(value)
    degrees = int(absolute)
    minutes_float = (absolute - degrees) * 60
    minutes = int(minutes_float)
    seconds = round((minutes_float - minutes) * 60, 3)
    if seconds >= 60:
        seconds -= 60
        minutes += 1
    if minutes >= 60:
        minutes -= 60
        degrees += 1
    return f'{degrees}° {minutes}\' {seconds}" {direction}'


def _dms_to_dec(raw: str, is_lat: bool) -> float:
    text = to_ascii_digits(raw).strip().upper()
    direction_match = re.search(r"[NSEW]", text)
    direction = direction_match.group(0) if direction_match else ""
    numbers = re.findall(r"-?\d+(?:\.\d+)?", re.sub(r"[NSEW]", "", text))
    if not numbers:
        raise ToolError(f"Invalid DMS value: {raw!r}")
    degrees = float(numbers[0])
    minutes = float(numbers[1]) if len(numbers) > 1 else 0.0
    seconds = float(numbers[2]) if len(numbers) > 2 else 0.0
    if minutes >= 60 or seconds >= 60 or minutes < 0 or seconds < 0:
        raise ToolError(f"Invalid minutes/seconds in: {raw!r}")
    value = abs(degrees) + minutes / 60 + seconds / 3600
    if degrees < 0 or direction in {"S", "W"}:
        value = -value
    limit = 90 if is_lat else 180
    if not -limit <= value <= limit:
        raise ToolError(f"Coordinate out of range: {raw!r}")
    return value


def decimal_to_dms(item: Input) -> Output:
    lat, lng = split_pipe(item.require_text(), 2, from_right=False, strip=True)
    latitude = parse_float(lat)
    longitude = parse_float(lng)
    if not -90 <= latitude <= 90:
        raise ToolError("Latitude must be between -90 and 90.")
    if not -180 <= longitude <= 180:
        raise ToolError("Longitude must be between -180 and 180.")
    return ok(f"{_dec_to_dms(latitude, True)}\n{_dec_to_dms(longitude, False)}", title="Decimal → DMS")


def dms_to_decimal(item: Input) -> Output:
    lat, lng = split_pipe(item.require_text(), 2, from_right=False, strip=True)
    return ok(
        f"{_dms_to_dec(lat, True):.6f}, {_dms_to_dec(lng, False):.6f}",
        title="DMS → Decimal",
    )


_register(make_tool("coordinate-converter", decimal_to_dms, title="Decimal → DMS", hint="lat|lng"))
_register(make_tool("coordinate-converter", dms_to_decimal, id="dms-to-decimal", title="DMS → Decimal", hint="lat DMS|lng DMS"))


# --------------------------------------------------------------------------
# Distance / bearing
# --------------------------------------------------------------------------

_COMPASS = ["North", "Northeast", "East", "Southeast", "South", "Southwest", "West", "Northwest"]


def geo_distance(item: Input) -> Output:
    parts = split_pipe(item.require_text(), 4, from_right=False, strip=True)
    lat1, lng1, lat2, lng2 = [parse_float(part) for part in parts]
    if abs(lat1) > 90 or abs(lat2) > 90:
        raise ToolError("Latitude must be between -90 and 90.")
    if abs(lng1) > 180 or abs(lng2) > 180:
        raise ToolError("Longitude must be between -180 and 180.")
    radius = 6371.0
    d_lat = math.radians(lat2 - lat1)
    d_lng = math.radians(lng2 - lng1)
    a = math.sin(d_lat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(d_lng / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    km = radius * c
    y = math.sin(math.radians(lng2 - lng1)) * math.cos(math.radians(lat2))
    x = math.cos(math.radians(lat1)) * math.sin(math.radians(lat2)) - math.sin(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.cos(math.radians(lng2 - lng1))
    bearing = (math.degrees(math.atan2(y, x)) + 360) % 360
    compass = _COMPASS[round(bearing / 45) % 8]
    return ok(
        "\n".join(
            [
                f"Distance (km): {km:.3f}",
                f"Distance (miles): {km * 0.621371:.3f}",
                f"Bearing: {bearing:.1f}°",
                f"Direction: {compass}",
            ]
        ),
        title="Geo Distance",
    )


_register(make_tool("geo-distance", geo_distance, title="Geo Distance", hint="lat1|lng1|lat2|lng2"))


# --------------------------------------------------------------------------
# Geohash
# --------------------------------------------------------------------------

_GEOHASH_BASE32 = "0123456789bcdefghjkmnpqrstuvwxyz"


def _geohash_encode(lat: float, lng: float, precision: int) -> str:
    lat_min, lat_max = -90.0, 90.0
    lng_min, lng_max = -180.0, 180.0
    output = ""
    bit = 0
    char = 0
    even = True
    while len(output) < precision:
        if even:
            mid = (lng_min + lng_max) / 2
            if lng >= mid:
                char = (char << 1) | 1
                lng_min = mid
            else:
                char <<= 1
                lng_max = mid
        else:
            mid = (lat_min + lat_max) / 2
            if lat >= mid:
                char = (char << 1) | 1
                lat_min = mid
            else:
                char <<= 1
                lat_max = mid
        even = not even
        bit += 1
        if bit == 5:
            output += _GEOHASH_BASE32[char]
            bit = 0
            char = 0
    return output


def _geohash_decode(value: str):
    lat_min, lat_max = -90.0, 90.0
    lng_min, lng_max = -180.0, 180.0
    even = True
    for char in value.lower():
        index = _GEOHASH_BASE32.find(char)
        if index == -1:
            raise ToolError(f"Invalid geohash character: {char!r}")
        for bit_position in range(4, -1, -1):
            bit = (index >> bit_position) & 1
            if even:
                mid = (lng_min + lng_max) / 2
                if bit:
                    lng_min = mid
                else:
                    lng_max = mid
            else:
                mid = (lat_min + lat_max) / 2
                if bit:
                    lat_min = mid
                else:
                    lat_max = mid
            even = not even
    return lat_min, lat_max, lng_min, lng_max


def geohash_encode(item: Input) -> Output:
    lat_text, lng_text, precision_text = split_pipe(item.require_text(), 3, from_right=False, strip=True)
    lat, lng = parse_float(lat_text), parse_float(lng_text)
    if abs(lat) > 90 or abs(lng) > 180:
        raise ToolError("Coordinate out of range.")
    precision = int(precision_text) if precision_text.isdigit() else 9
    return ok(_geohash_encode(lat, lng, max(1, min(12, precision))), title="Geohash Encode")


def geohash_decode(item: Input) -> Output:
    lat_min, lat_max, lng_min, lng_max = _geohash_decode(item.require_text().strip())
    return ok(
        "\n".join(
            [
                f"Latitude: {(lat_min + lat_max) / 2:.6f}",
                f"Longitude: {(lng_min + lng_max) / 2:.6f}",
                f"SW: {lat_min:.6f}, {lng_min:.6f}",
                f"NE: {lat_max:.6f}, {lng_max:.6f}",
            ]
        ),
        title="Geohash Decode",
    )


_register(make_tool("geohash", geohash_encode, title="Geohash Encode", hint="lat|lng|precision"))
_register(make_tool("geohash", geohash_decode, id="geohash-decode", title="Geohash Decode", hint="geohash"))


# --------------------------------------------------------------------------
# GeoJSON
# --------------------------------------------------------------------------

_GEOJSON_TYPES = {
    "FeatureCollection", "Feature", "Point", "MultiPoint", "LineString",
    "MultiLineString", "Polygon", "MultiPolygon", "GeometryCollection",
}


def _walk_coords(node, box):
    if not isinstance(node, list):
        return
    if len(node) >= 2 and isinstance(node[0], (int, float)) and isinstance(node[1], (int, float)):
        lng, lat = node[0], node[1]
        box[0] = min(box[0], lng)
        box[1] = min(box[1], lat)
        box[2] = max(box[2], lng)
        box[3] = max(box[3], lat)
        return
    for child in node:
        _walk_coords(child, box)


def _geojson(mode: str):
    def run(item: Input) -> Output:
        try:
            data = json.loads(item.require_text())
        except Exception as exc:
            raise ToolError(f"Invalid JSON: {exc}") from exc
        if not isinstance(data, dict) or data.get("type") not in _GEOJSON_TYPES:
            raise ToolError("Not a valid GeoJSON object.")
        features = 1
        geometries = []
        if data.get("type") == "FeatureCollection":
            features = len(data.get("features") or [])
            geometries = [feature.get("geometry") for feature in data.get("features") or [] if feature.get("geometry")]
        elif data.get("type") == "Feature":
            geometries = [data.get("geometry")]
        elif data.get("type") == "GeometryCollection":
            features = len(data.get("geometries") or [])
            geometries = data.get("geometries") or []
        else:
            geometries = [data]
        box = [math.inf, math.inf, -math.inf, -math.inf]
        for geometry in geometries:
            if isinstance(geometry, dict):
                _walk_coords(geometry.get("coordinates"), box)
                if geometry.get("type") == "GeometryCollection":
                    for child in geometry.get("geometries") or []:
                        _walk_coords(child.get("coordinates"), box)
        has_box = math.isfinite(box[0])
        formatted = json.dumps(data, ensure_ascii=False, indent=2 if mode == "pretty" else None, separators=None if mode == "pretty" else (",", ":"))
        return ok(
            "\n".join(
                [
                    f"Type: {data.get('type')}",
                    f"Features/geometries: {features}",
                    f"SW: {box[1]:.4f}, {box[0]:.4f}" if has_box else "SW: -",
                    f"NE: {box[3]:.4f}, {box[2]:.4f}" if has_box else "NE: -",
                    "",
                    formatted,
                ]
            ),
            title="GeoJSON Tools",
        )

    return run


_register(make_tool("geojson-tools", _geojson("pretty"), title="GeoJSON Formatter", hint="clipboard GeoJSON"))
_register(make_tool("geojson-tools", _geojson("minify"), id="geojson-minify", title="GeoJSON Minifier", hint="clipboard GeoJSON"))


# --------------------------------------------------------------------------
# Polyline
# --------------------------------------------------------------------------

def _encode_value(value: int) -> str:
    value = ~(value << 1) if value < 0 else value << 1
    output = ""
    while value >= 0x20:
        output += chr((0x20 | (value & 0x1F)) + 63)
        value >>= 5
    output += chr(value + 63)
    return output


def _polyline_encode(points: list[tuple[float, float]]) -> str:
    output = ""
    last_lat = last_lng = 0
    for lat, lng in points:
        ilat = round(lat * 1e5)
        ilng = round(lng * 1e5)
        output += _encode_value(ilat - last_lat)
        output += _encode_value(ilng - last_lng)
        last_lat, last_lng = ilat, ilng
    return output


def _polyline_decode(value: str) -> list[tuple[float, float]]:
    points = []
    index = lat = lng = 0
    while index < len(value):
        result = shift = 0
        while True:
            byte = ord(value[index]) - 63
            index += 1
            result |= (byte & 0x1F) << shift
            shift += 5
            if byte < 0x20:
                break
        lat += ~(result >> 1) if result & 1 else result >> 1
        result = shift = 0
        while True:
            byte = ord(value[index]) - 63
            index += 1
            result |= (byte & 0x1F) << shift
            shift += 5
            if byte < 0x20:
                break
        lng += ~(result >> 1) if result & 1 else result >> 1
        points.append((lat / 1e5, lng / 1e5))
    return points


def polyline_encode(item: Input) -> Output:
    points = []
    for line in to_ascii_digits(item.require_text()).splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(",")
        if len(parts) < 2:
            raise ToolError(f"Invalid point: {line}")
        points.append((float(parts[0]), float(parts[1])))
    if not points:
        raise ToolError("No points found.")
    return ok(_polyline_encode(points), title="Polyline Encode")


def polyline_decode(item: Input) -> Output:
    points = _polyline_decode(item.require_text().strip())
    return ok("\n".join(f"{lat},{lng}" for lat, lng in points), title="Polyline Decode")


_register(make_tool("polyline", polyline_encode, title="Polyline Encode", hint="lat,lng per line"))
_register(make_tool("polyline", polyline_decode, id="polyline-decode", title="Polyline Decode", hint="encoded polyline"))
