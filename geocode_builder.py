#!/usr/bin/env python3
"""
独立的地理编码生成/更新脚本。

目标：
1) 生成/更新缓存结构：城市 -> 地址 -> 坐标
2) 构建德国全国 Spatial Hashing / Grid Index：格子 -> 80 城市之一
3) 支持旧版缓存（地址 -> 坐标）迁移
"""
import json
import math
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

BASE_DIR = Path(__file__).resolve().parent
SUPERMARKETS_FILE = BASE_DIR / "Supermarkets.txt"
GEOCODE_CACHE_FILE = BASE_DIR / "geocode_cache.json"
CITY_NAME_FILE = BASE_DIR / "city_name.txt"

DEFAULT_CITY = "Erlangen"

# Brand switches: set to False to ignore this supermarket brand entirely.
ENABLE_EDEKA = True
ENABLE_REWE = False
ENABLE_KAUFLAND = False
ENABLE_ALDI_NORD = True
ENABLE_ALDI_SUED = False
ENABLE_LIDL = True
ENABLE_NETTO = True
ENABLE_PENNY = True
ENABLE_NORMA = True

BRAND_ENABLED = {
    "Edeka": ENABLE_EDEKA,
    "Rewe": ENABLE_REWE,
    "Kaufland": ENABLE_KAUFLAND,
    "Aldi Nord": ENABLE_ALDI_NORD,
    "Aldi Süd": ENABLE_ALDI_SUED,
    "Lidl": ENABLE_LIDL,
    "Netto": ENABLE_NETTO,
    "Penny": ENABLE_PENNY,
    "Norma": ENABLE_NORMA,
}

GERMANY_BOUNDS = {
    "min_lat": 47.0,
    "max_lat": 55.5,
    "min_lon": 5.0,
    "max_lon": 15.8,
}

GRID_CELL_SIZE = 0.25
MARKET_CHECKPOINT_INTERVAL = 10
DIRECT_COORD_BRANDS = {"Kaufland"}

ZIP_CITY_REGEX = re.compile(r"\b\d{5}\s+([^,]+)$")
TRAILING_COORDS_REGEX = re.compile(
    r"^(?P<address>.*?),\s*(?P<lat>-?\d+(?:\.\d+)?),\s*(?P<lon>-?\d+(?:\.\d+)?)$"
)


def normalize_city_name(city: str) -> str:
    return re.sub(r"\s+", " ", city).strip()


def detect_city(address: str) -> str:
    """
    城市以地址中“邮编后的城市”字段为准。
    例如：Waldstraße 101, 90763 Fürth -> Fürth
    """
    parts = [part.strip() for part in address.split(",")]
    for part in parts:
        matched = ZIP_CITY_REGEX.search(part)
        if matched:
            return normalize_city_name(matched.group(1))
    return DEFAULT_CITY


def load_city_name_list(path: Path):
    if not path.exists():
        raise FileNotFoundError(f"{path} not found")
    cities = []
    seen = set()
    with path.open("r", encoding="utf-8") as f:
        for raw_line in f:
            city = normalize_city_name(raw_line)
            if not city:
                continue
            if city in seen:
                continue
            seen.add(city)
            cities.append(city)
    return cities


def parse_supermarkets(file_path: Path):
    """解析 Supermarkets.txt 文件，返回市场列表。"""
    markets = []
    current_brand = None
    market_id = 1

    with file_path.open("r", encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line:
                continue
            if "," not in line:
                current_brand = line
                continue
            if current_brand is None:
                continue
            if not BRAND_ENABLED.get(current_brand, True):
                continue

            coords_match = TRAILING_COORDS_REGEX.match(line)
            if coords_match:
                address = coords_match.group("address").strip()
                provided_geo = {
                    "lat": float(coords_match.group("lat")),
                    "lon": float(coords_match.group("lon")),
                }
            else:
                address = line
                provided_geo = None

            city = detect_city(address)
            zip_code_match = re.search(r"\b\d{5}\b", address)
            zip_code = zip_code_match.group(0) if zip_code_match else ""
            query = f"{address}, Germany"
            markets.append(
                {
                    "id": market_id,
                    "brand": current_brand,
                    "address": address,
                    "city": city,
                    "zip": zip_code,
                    "query": query,
                    "provided_geo": provided_geo,
                }
            )
            market_id += 1

    return markets


def load_geocode_cache(path: Path):
    """加载现有缓存，如果不存在则返回空字典。"""
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_geocode_cache(path: Path, cache):
    """保存地理编码缓存。"""
    with path.open("w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def write_market_record_if_missing(path: Path, market: dict, geo: Optional[Dict[str, float]]) -> bool:
    """Write one market record immediately if it does not exist in structured cache."""
    cache = load_geocode_cache(path) if path.exists() else {}
    if not isinstance(cache, dict):
        cache = {}

    cities = cache.setdefault("cities", {})
    if not isinstance(cities, dict):
        cities = {}
        cache["cities"] = cities

    city_name = market["city"] or DEFAULT_CITY
    city_entry = cities.setdefault(city_name, {})
    if not isinstance(city_entry, dict):
        city_entry = {}
        cities[city_name] = city_entry

    brand = market["brand"]
    brand_bucket = city_entry.setdefault(brand, {})
    if not isinstance(brand_bucket, dict):
        brand_bucket = {}
        city_entry[brand] = brand_bucket

    address = market["address"]
    if address in brand_bucket:
        return False

    brand_bucket[address] = {
        "lat": geo["lat"] if geo else None,
        "lon": geo["lon"] if geo else None,
        "zip": market["zip"],
    }
    save_geocode_cache(path, cache)
    return True


def geocode_address(query: str):
    """调用 Nominatim API 进行地理编码，返回坐标或 None。"""
    encoded_query = urllib.parse.quote(query)
    url = (
        "https://nominatim.openstreetmap.org/search"
        f"?q={encoded_query}&format=json&limit=1"
    )
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "FindLEggs/1.0 (lightweight local app)",
            "Accept": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            data = json.loads(response.read().decode("utf-8"))
            if not data:
                return None
            first = data[0]
            return {
                "lat": float(first["lat"]),
                "lon": float(first["lon"]),
            }
    except Exception as e:
        print(f"  Error geocoding {query}: {e}")
        return None


def parse_cached_market_geo(cache_obj: dict):
    """
    仅读取新格式缓存：
    - { "cities": { city: { brand: { address: {"lat":..., "lon":...}}}}}

    说明：
    - 如果 lat/lon 为 None，视为无效缓存，不写入 market_geo（后续会重新 geocode）
    """
    market_geo = {}

    cities = cache_obj.get("cities") if isinstance(cache_obj, dict) else None
    if isinstance(cities, dict):
        for city_entry in cities.values():
            if not isinstance(city_entry, dict):
                continue
            # 迭代所有品牌（brand）
            for brand_entry in city_entry.values():
                if not isinstance(brand_entry, dict):
                    continue
                # 迭代品牌下的所有地址
                for address, geo in brand_entry.items():
                    if not isinstance(geo, dict):
                        continue
                    lat_raw = geo.get("lat")
                    lon_raw = geo.get("lon")
                    if lat_raw is None or lon_raw is None:
                        continue
                    try:
                        market_geo[address] = {"lat": float(lat_raw), "lon": float(lon_raw)}
                    except (TypeError, ValueError):
                        # 非法坐标按无效缓存处理，后续会重新 geocode
                        continue

    return market_geo


def parse_cached_city_centers(cache_obj: dict):
    city_centers = {}
    spatial = cache_obj.get("spatial_index") if isinstance(cache_obj, dict) else None
    if not isinstance(spatial, dict):
        return city_centers
    centers = spatial.get("city_centers")
    if not isinstance(centers, dict):
        return city_centers
    for city, geo in centers.items():
        if isinstance(geo, dict) and "lat" in geo and "lon" in geo:
            city_centers[city] = {"lat": float(geo["lat"]), "lon": float(geo["lon"])}
    return city_centers


def sync_city_centers_with_city_list(cities_from_file, cached_city_centers):
    """
    将 city_name.txt 与缓存 city_centers 做对比并增量同步：
    - 删除：缓存中存在但列表中不存在的城市
    - 新增：列表中存在但缓存中不存在的城市（后续再 geocode）
    """
    target_cities = [normalize_city_name(city) for city in cities_from_file if normalize_city_name(city)]
    if DEFAULT_CITY not in target_cities:
        target_cities.append(DEFAULT_CITY)

    target_set = set(target_cities)
    cached_set = set(cached_city_centers.keys())

    removed_cities = sorted(cached_set - target_set)
    added_cities = [city for city in target_cities if city not in cached_set]
    kept_count = len(cached_set & target_set)

    for city in removed_cities:
        del cached_city_centers[city]

    return {
        "target_cities": target_cities,
        "added_cities": added_cities,
        "removed_cities": removed_cities,
        "kept_count": kept_count,
    }


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lam = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lam / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return r * c


def build_nearby_cities(city_centers: Dict[str, Dict[str, float]], limit: int = 3):
    nearby_cities = {}
    for city, origin in city_centers.items():
        if not isinstance(origin, dict):
            continue

        origin_lat = origin.get("lat")
        origin_lon = origin.get("lon")
        if not isinstance(origin_lat, (int, float)) or not isinstance(origin_lon, (int, float)):
            continue

        distances = []
        for other_city, geo in city_centers.items():
            if other_city == city or not isinstance(geo, dict):
                continue
            other_lat = geo.get("lat")
            other_lon = geo.get("lon")
            if not isinstance(other_lat, (int, float)) or not isinstance(other_lon, (int, float)):
                continue

            dist = haversine_km(float(origin_lat), float(origin_lon), float(other_lat), float(other_lon))
            distances.append(
                {
                    "city": other_city,
                    "lat": float(other_lat),
                    "lon": float(other_lon),
                    "distance_km": round(dist, 1),
                }
            )

        distances.sort(key=lambda item: (item["distance_km"], item["city"]))
        nearby_cities[city] = distances[:limit]

    return nearby_cities


def geocode_city_center(city: str) -> Optional[Dict[str, float]]:
    return geocode_address(f"{city}, Germany")


def nearest_city_for_point(lat: float, lon: float, city_centers: Dict[str, Dict[str, float]]) -> str:
    if (
        lat < GERMANY_BOUNDS["min_lat"]
        or lat > GERMANY_BOUNDS["max_lat"]
        or lon < GERMANY_BOUNDS["min_lon"]
        or lon > GERMANY_BOUNDS["max_lon"]
    ):
        return DEFAULT_CITY

    nearest_city = DEFAULT_CITY
    nearest_distance = float("inf")
    for city, geo in city_centers.items():
        dist = haversine_km(lat, lon, geo["lat"], geo["lon"])
        if dist < nearest_distance:
            nearest_distance = dist
            nearest_city = city
    return nearest_city


def build_spatial_index(city_centers: Dict[str, Dict[str, float]]):
    min_lat = GERMANY_BOUNDS["min_lat"]
    max_lat = GERMANY_BOUNDS["max_lat"]
    min_lon = GERMANY_BOUNDS["min_lon"]
    max_lon = GERMANY_BOUNDS["max_lon"]

    rows = int(math.ceil((max_lat - min_lat) / GRID_CELL_SIZE))
    cols = int(math.ceil((max_lon - min_lon) / GRID_CELL_SIZE))

    cells = {}
    for row in range(rows):
        for col in range(cols):
            lat = min_lat + (row + 0.5) * GRID_CELL_SIZE
            lon = min_lon + (col + 0.5) * GRID_CELL_SIZE
            city = nearest_city_for_point(lat, lon, city_centers)
            cells[f"{row}:{col}"] = city

    return {
        "default_city": DEFAULT_CITY,
        "cell_size": GRID_CELL_SIZE,
        "bounds": GERMANY_BOUNDS,
        "rows": rows,
        "cols": cols,
        "city_centers": city_centers,
        "nearby_cities": build_nearby_cities(city_centers),
        "cells": cells,
    }


def build_or_update_cache():
    """
    生成或更新地理编码缓存。
    - 如果缓存不存在，从头开始编码所有地址
    - 如果缓存存在，只补齐值为 null 的地址
    """
    if not SUPERMARKETS_FILE.exists():
        print(f"Error: {SUPERMARKETS_FILE} not found")
        return

    markets = parse_supermarkets(SUPERMARKETS_FILE)
    cities_80 = load_city_name_list(CITY_NAME_FILE)
    cache = load_geocode_cache(GEOCODE_CACHE_FILE)
    market_geo = parse_cached_market_geo(cache)
    city_centers = parse_cached_city_centers(cache)
    city_diff = sync_city_centers_with_city_list(cities_80, city_centers)

    total = len(markets)
    success_count = 0
    failed_count = 0
    skipped_count = 0
    newly_geocoded = 0
    from_file_coords_count = 0
    inserted_record_count = 0
    cached_market_count_before = len(market_geo)

    for idx, market in enumerate(markets, 1):
        key = market["query"]
        address_key = market["address"]

        # 如果已在缓存中且有坐标，跳过
        cached_geo = market_geo.get(key)
        if cached_geo is None:
            cached_geo = market_geo.get(address_key)
        if cached_geo is not None:
            success_count += 1
            skipped_count += 1
            print(f"[{idx}/{total}] SKIP (cached) {market['brand']} - {market['address']}")
            if write_market_record_if_missing(GEOCODE_CACHE_FILE, market, cached_geo):
                inserted_record_count += 1
            continue

        if market["brand"] in DIRECT_COORD_BRANDS:
            provided_geo = market.get("provided_geo")
            if isinstance(provided_geo, dict):
                market_geo[key] = provided_geo
                market_geo[address_key] = provided_geo
                success_count += 1
                from_file_coords_count += 1
                print(
                    f"[{idx}/{total}] DIRECT COORDS {market['brand']} - {market['address']}"
                    f" -> ({provided_geo['lat']:.6f}, {provided_geo['lon']:.6f})"
                )
            else:
                market_geo[key] = None
                market_geo[address_key] = None
                failed_count += 1
                print(
                    f"[{idx}/{total}] MISSING DIRECT COORDS {market['brand']} - {market['address']}"
                )
            if write_market_record_if_missing(GEOCODE_CACHE_FILE, market, market_geo.get(key)):
                inserted_record_count += 1
            continue

        # 如果在缓存中但是 null，或者不在缓存中，需要编码
        print(f"[{idx}/{total}] GEOCODING {market['brand']} - {market['address']}")
        result = geocode_address(key)

        if result:
            market_geo[key] = result
            market_geo[address_key] = result
            success_count += 1
            newly_geocoded += 1
            print(f"        Success: ({result['lat']:.6f}, {result['lon']:.6f})")
        else:
            market_geo[key] = None
            market_geo[address_key] = None
            failed_count += 1
            print("        Failed")

        if write_market_record_if_missing(GEOCODE_CACHE_FILE, market, market_geo.get(key)):
            inserted_record_count += 1

        time.sleep(1.05)

    print(f"Building city centers incrementally for {len(city_diff['target_cities'])} cities...")
    for idx, city in enumerate(city_diff["target_cities"], 1):
        if city in city_centers:
            print(f"[{idx}/{len(city_diff['target_cities'])}] SKIP city center cached: {city}")
            continue
        result = geocode_city_center(city)
        if result:
            city_centers[city] = result
            print(f"[{idx}/{len(city_diff['target_cities'])}] city center: {city} -> ({result['lat']:.6f}, {result['lon']:.6f})")
        else:
            print(f"[{idx}/{len(city_diff['target_cities'])}] city center geocode failed: {city}")
        time.sleep(1.05)

    if DEFAULT_CITY not in city_centers:
        default_geo = geocode_city_center(DEFAULT_CITY)
        if default_geo:
            city_centers[DEFAULT_CITY] = default_geo

    spatial_index = build_spatial_index(city_centers)
    final_cache = load_geocode_cache(GEOCODE_CACHE_FILE)
    if not isinstance(final_cache, dict):
        final_cache = {}
    final_cache["meta"] = {
        "schema_version": 3,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "default_city": DEFAULT_CITY,
    }
    final_cache["spatial_index"] = spatial_index
    if "cities" not in final_cache or not isinstance(final_cache.get("cities"), dict):
        final_cache["cities"] = {}

    save_geocode_cache(GEOCODE_CACHE_FILE, final_cache)

    print()
    print("=" * 50)
    print("Geocoding Summary")
    print("=" * 50)
    print(f"Total markets: {total}")
    print(f"Successful (cached + newly): {success_count}")
    print(f"  - Skipped (already cached): {skipped_count}")
    print(f"  - Loaded from file coords: {from_file_coords_count}")
    print(f"  - Newly geocoded: {newly_geocoded}")
    print(f"  - Inserted new market records to cache: {inserted_record_count}")
    print(f"Failed: {failed_count}")
    print(f"Cached market geocodes before: {cached_market_count_before}")
    print(f"Cached market geocodes after: {len(market_geo)}")
    print(f"Timestamp: {datetime.now(timezone.utc).isoformat()}")
    print()

    print("City center diff summary")
    print(f"  - In city_name.txt (plus default): {len(city_diff['target_cities'])}")
    print(f"  - Already cached and kept: {city_diff['kept_count']}")
    print(f"  - Added: {len(city_diff['added_cities'])}")
    print(f"  - Removed: {len(city_diff['removed_cities'])}")
    if city_diff["removed_cities"]:
        print(f"  - Removed cities: {', '.join(city_diff['removed_cities'])}")
    print()

    print(f"Cache saved to {GEOCODE_CACHE_FILE}")


if __name__ == "__main__":
    build_or_update_cache()
