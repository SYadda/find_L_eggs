#!/usr/bin/env python3
"""
独立的地理编码生成/更新脚本。
- 如果不存在 geocode_cache.json，从头开始编码所有地址
- 如果已存在 geocode_cache.json，只补齐 null 的地址，已有坐标的保留
"""
import json
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
SUPERMARKETS_FILE = BASE_DIR / "Supermarkets.txt"
GEOCODE_CACHE_FILE = BASE_DIR / "geocode_cache.json"

CITY_BY_ADDRESS_PATTERN = [
    (re.compile(r"\bErlangen\b", re.IGNORECASE), "Erlangen"),
    (re.compile(r"\bFürth\b", re.IGNORECASE), "Fürth"),
    (re.compile(r"\bNürnberg\b", re.IGNORECASE), "Nürnberg"),
]


def detect_city(address: str) -> str:
    for pattern, city_name in CITY_BY_ADDRESS_PATTERN:
        if pattern.search(address):
            return city_name
    return "Unknown"


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

            city = detect_city(line)
            zip_code_match = re.search(r"\b\d{5}\b", line)
            zip_code = zip_code_match.group(0) if zip_code_match else ""
            query = f"{line}, Germany"
            markets.append(
                {
                    "id": market_id,
                    "brand": current_brand,
                    "address": line,
                    "city": city,
                    "zip": zip_code,
                    "query": query,
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
    cache = load_geocode_cache(GEOCODE_CACHE_FILE)

    total = len(markets)
    success_count = 0
    failed_count = 0
    skipped_count = 0
    newly_geocoded = 0

    print(f"Processing {total} markets...")
    print(f"Cache size before: {len(cache)}")
    print()

    for idx, market in enumerate(markets, 1):
        key = market["query"]

        # 如果已在缓存中且有坐标，跳过
        if key in cache and cache[key] is not None:
            success_count += 1
            skipped_count += 1
            print(f"[{idx}/{total}] ✓ SKIP (cached) {market['brand']} - {market['address']}")
            continue

        # 如果在缓存中但是 null，或者不在缓存中，需要编码
        print(f"[{idx}/{total}] ⟳ GEOCODING {market['brand']} - {market['address']}")
        result = geocode_address(key)

        if result:
            cache[key] = result
            success_count += 1
            newly_geocoded += 1
            print(f"        → Success: ({result['lat']:.6f}, {result['lon']:.6f})")
        else:
            cache[key] = None
            failed_count += 1
            print(f"        → Failed")

        # Respect Nominatim usage policy
        time.sleep(1.05)

    print()
    print("=" * 50)
    print("Geocoding Summary")
    print("=" * 50)
    print(f"Total markets: {total}")
    print(f"Successful (cached + newly): {success_count}")
    print(f"  - Skipped (already cached): {skipped_count}")
    print(f"  - Newly geocoded: {newly_geocoded}")
    print(f"Failed: {failed_count}")
    print(f"Cache size after: {len(cache)}")
    print(f"Timestamp: {datetime.now(timezone.utc).isoformat()}")
    print()

    save_geocode_cache(GEOCODE_CACHE_FILE, cache)
    print(f"Cache saved to {GEOCODE_CACHE_FILE}")


if __name__ == "__main__":
    build_or_update_cache()
