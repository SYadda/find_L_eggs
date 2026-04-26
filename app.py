#!/usr/bin/env python3
import json
import math
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

BASE_DIR = Path(__file__).resolve().parent
SUPERMARKETS_FILE = BASE_DIR / "Supermarkets.txt"
GEOCODE_CACHE_FILE = BASE_DIR / "geocode_cache.json"
DB_FILE = BASE_DIR / "votes.db"

HOST = "127.0.0.1"
PORT = 8000
VOTE_TTL_HOURS = 12
SAME_STATUS_COOLDOWN_HOURS = 1
RECENT_DARK_HOURS = 3
VOTE_THRESHOLD = 3

DEFAULT_CITY = "Erlangen"
VALID_STATUSES = {"plenty", "few", "none"}
ZIP_CITY_REGEX = re.compile(r"\b\d{5}\s+([^,]+)$")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def normalize_city_name(city: str) -> str:
    return re.sub(r"\s+", " ", city).strip()


def detect_city(address: str) -> str:
    parts = [part.strip() for part in address.split(",")]
    for part in parts:
        matched = ZIP_CITY_REGEX.search(part)
        if matched:
            return normalize_city_name(matched.group(1))
    return DEFAULT_CITY


def parse_supermarkets(file_path: Path):
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
            markets.append(
                {
                    "id": market_id,
                    "brand": current_brand,
                    "address": line,
                    "city": city,
                    "zip": zip_code,
                }
            )
            market_id += 1

    return markets


def load_geocode_cache(path: Path):
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def geocode_lookup_from_cache(cache):
    """兼容新旧缓存结构，输出 address -> geo 映射。"""
    lookup = {}

    cities = cache.get("cities") if isinstance(cache, dict) else None
    if isinstance(cities, dict):
        for city_entry in cities.values():
            if not isinstance(city_entry, dict):
                continue
            markets = city_entry.get("markets")
            if not isinstance(markets, dict):
                continue
            for address, geo in markets.items():
                if isinstance(geo, dict) and geo.get("lat") is not None and geo.get("lon") is not None:
                    lookup[address] = {"lat": float(geo["lat"]), "lon": float(geo["lon"])}

    for key, value in cache.items() if isinstance(cache, dict) else []:
        if key in {"meta", "cities", "spatial_index"}:
            continue
        if isinstance(value, dict) and value.get("lat") is not None and value.get("lon") is not None:
            address = key[:-9] if key.endswith(", Germany") else key
            lookup[address] = {"lat": float(value["lat"]), "lon": float(value["lon"])}

    return lookup


def enrich_with_coordinates(markets, cache):
    lookup = geocode_lookup_from_cache(cache)
    for market in markets:
        geo = lookup.get(market["address"])
        market["lat"] = geo["lat"] if geo else None
        market["lon"] = geo["lon"] if geo else None
    return markets


def get_spatial_index(cache):
    spatial = cache.get("spatial_index") if isinstance(cache, dict) else None
    if not isinstance(spatial, dict):
        return None
    cells = spatial.get("cells")
    bounds = spatial.get("bounds")
    if not isinstance(cells, dict) or not isinstance(bounds, dict):
        return None
    return spatial


def get_nearby_cities_for_city(spatial_index, city: str):
    if not isinstance(spatial_index, dict):
        return []
    nearby_cities = spatial_index.get("nearby_cities")
    if not isinstance(nearby_cities, dict):
        return []
    city_nearby = nearby_cities.get(city)
    if not isinstance(city_nearby, list):
        return []
    return city_nearby


def city_from_center(lat: float, lon: float, spatial_index):
    if not spatial_index:
        return DEFAULT_CITY

    bounds = spatial_index.get("bounds", {})
    cell_size = float(spatial_index.get("cell_size", 0.25))
    rows = int(spatial_index.get("rows", 0))
    cols = int(spatial_index.get("cols", 0))
    default_city = spatial_index.get("default_city", DEFAULT_CITY)
    cells = spatial_index.get("cells", {})

    min_lat = float(bounds.get("min_lat", 47.0))
    max_lat = float(bounds.get("max_lat", 55.5))
    min_lon = float(bounds.get("min_lon", 5.0))
    max_lon = float(bounds.get("max_lon", 15.8))

    if lat < min_lat or lat > max_lat or lon < min_lon or lon > max_lon:
        return default_city

    row = int(math.floor((lat - min_lat) / cell_size))
    col = int(math.floor((lon - min_lon) / cell_size))

    if row < 0 or row >= rows or col < 0 or col >= cols:
        return default_city

    return cells.get(f"{row}:{col}", default_city)


def init_db():
    conn = sqlite3.connect(DB_FILE)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS markets (
            id INTEGER PRIMARY KEY,
            brand TEXT NOT NULL,
            address TEXT NOT NULL UNIQUE,
            city TEXT NOT NULL,
            zip TEXT,
            lat REAL,
            lon REAL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS votes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            market_id INTEGER NOT NULL,
            ip TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (market_id) REFERENCES markets(id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS vote_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            market_id INTEGER NOT NULL,
            market_address TEXT NOT NULL,
            status TEXT NOT NULL,
            ip TEXT NOT NULL,
            created_at TEXT NOT NULL,
            accepted INTEGER NOT NULL,
            FOREIGN KEY (market_id) REFERENCES markets(id)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_votes_market_created ON votes(market_id, created_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_votes_ip_market_status_created ON votes(ip, market_id, status, created_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_markets_city ON markets(city)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_vote_events_created ON vote_events(created_at)")
    conn.commit()
    conn.close()


def sync_markets_to_db(markets):
    conn = sqlite3.connect(DB_FILE)
    try:
        conn.execute("DELETE FROM markets")
        conn.executemany(
            """
            INSERT INTO markets (id, brand, address, city, zip, lat, lon)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    m["id"],
                    m["brand"],
                    m["address"],
                    m["city"],
                    m["zip"],
                    m["lat"],
                    m["lon"],
                )
                for m in markets
            ],
        )
        conn.commit()
    finally:
        conn.close()


def cleanup_expired_votes(conn):
    cutoff = (utc_now() - timedelta(hours=VOTE_TTL_HOURS)).isoformat()
    conn.execute("DELETE FROM votes WHERE created_at < ?", (cutoff,))


def query_markets_by_city(conn, city: str):
    cursor = conn.execute(
        """
        SELECT id, brand, address, city, zip, lat, lon
        FROM markets
        WHERE city = ?
        ORDER BY brand, address
        """,
        (city,),
    )
    return [
        {
            "id": row[0],
            "brand": row[1],
            "address": row[2],
            "city": row[3],
            "zip": row[4],
            "lat": row[5],
            "lon": row[6],
        }
        for row in cursor.fetchall()
    ]


def query_all_markets(conn):
    cursor = conn.execute(
        """
        SELECT id, brand, address, city, zip, lat, lon
        FROM markets
        ORDER BY city, brand, address
        """
    )
    return [
        {
            "id": row[0],
            "brand": row[1],
            "address": row[2],
            "city": row[3],
            "zip": row[4],
            "lat": row[5],
            "lon": row[6],
        }
        for row in cursor.fetchall()
    ]


def query_vote_counts(conn, market_ids):
    if not market_ids:
        return {}
    placeholders = ",".join("?" for _ in market_ids)
    cursor = conn.execute(
        f"""
        SELECT market_id,
               SUM(CASE WHEN status = 'plenty' THEN 1 ELSE 0 END) AS plenty,
               SUM(CASE WHEN status = 'few' THEN 1 ELSE 0 END) AS few,
               SUM(CASE WHEN status = 'none' THEN 1 ELSE 0 END) AS none
        FROM votes
        WHERE market_id IN ({placeholders})
        GROUP BY market_id
        """,
        market_ids,
    )
    counts_map = {}
    for market_id, plenty, few, none in cursor.fetchall():
        counts_map[market_id] = {
            "plenty": int(plenty or 0),
            "few": int(few or 0),
            "none": int(none or 0),
        }
    return counts_map


def query_vote_details(conn, market_ids):
    if not market_ids:
        return {}
    placeholders = ",".join("?" for _ in market_ids)
    cursor = conn.execute(
        f"""
        SELECT id, market_id, status, created_at
        FROM votes
        WHERE market_id IN ({placeholders})
        ORDER BY market_id ASC, created_at ASC
        """,
        market_ids,
    )
    details_map = {market_id: [] for market_id in market_ids}
    now = utc_now()
    for vote_id, market_id, status, created_at_str in cursor.fetchall():
        created_at = datetime.fromisoformat(created_at_str)
        expires_at = created_at + timedelta(hours=VOTE_TTL_HOURS)
        remaining_seconds = int((expires_at - now).total_seconds())
        if remaining_seconds < 0:
            continue
        details_map[market_id].append(
            {
                "vote_id": vote_id,
                "status": status,
                "created_at": created_at.isoformat(),
                "expires_at": expires_at.isoformat(),
                "remaining_seconds": remaining_seconds,
            }
        )
    return details_map


def determine_display_status(counts, vote_details):
    max_votes = max(counts.values())
    if max_votes == 0:
        return "unknown"

    top_statuses = [k for k, v in counts.items() if v == max_votes]
    winning_status = top_statuses[0]
    if len(top_statuses) > 1:
        for vote in reversed(vote_details):
            if vote["status"] in top_statuses:
                winning_status = vote["status"]
                break

    if max_votes < VOTE_THRESHOLD:
        return f"{winning_status}_light"

    if not vote_details:
        return f"{winning_status}_light"
    latest_vote_created_at = datetime.fromisoformat(vote_details[-1]["created_at"])
    dark_cutoff = utc_now() - timedelta(hours=RECENT_DARK_HOURS)
    if latest_vote_created_at >= dark_cutoff:
        return winning_status
    return f"{winning_status}_light"


def market_payload(market, counts, vote_details):
    return {
        "id": market["id"],
        "brand": market["brand"],
        "address": market["address"],
        "city": market["city"],
        "zip": market["zip"],
        "lat": market["lat"],
        "lon": market["lon"],
        "counts": counts,
        "display_status": determine_display_status(counts, vote_details),
    }


def build_markets_payload(conn, markets, include_details=False, include_only_valid=False):
    market_ids = [m["id"] for m in markets]
    counts_map = query_vote_counts(conn, market_ids)
    details_map = query_vote_details(conn, market_ids)

    payload = []
    for market in markets:
        counts = counts_map.get(market["id"], {"plenty": 0, "few": 0, "none": 0})
        vote_details = details_map.get(market["id"], [])
        total_votes = len(vote_details)

        if include_only_valid and total_votes == 0:
            continue

        row = market_payload(market, counts, vote_details)
        row["total_votes"] = total_votes
        if include_details:
            row["vote_details"] = vote_details
        payload.append(row)
    return payload


class AppState:
    def __init__(self, markets, spatial_index):
        self.markets = markets
        self.market_by_id = {m["id"]: m for m in markets}
        self.spatial_index = spatial_index


class Handler(BaseHTTPRequestHandler):
    state = None

    def _read_json(self):
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return None
        raw = self.rfile.read(length).decode("utf-8")
        return json.loads(raw)

    def _send_json(self, payload, status=HTTPStatus.OK):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: Path, content_type: str):
        if not path.exists() or not path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        data = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        route_path = urlsplit(self.path).path

        if route_path == "/" or route_path == "/index.html":
            return self._send_file(BASE_DIR / "index.html", "text/html; charset=utf-8")
        if route_path == "/overview" or route_path == "/overview.html":
            return self._send_file(BASE_DIR / "overview.html", "text/html; charset=utf-8")
        if route_path == "/styles.css":
            return self._send_file(BASE_DIR / "styles.css", "text/css; charset=utf-8")
        if route_path == "/app.js":
            return self._send_file(BASE_DIR / "app.js", "application/javascript; charset=utf-8")
        if route_path == "/overview.js":
            return self._send_file(BASE_DIR / "overview.js", "application/javascript; charset=utf-8")
        if route_path == "/api/config":
            return self._send_json(
                {
                    "vote_ttl_hours": VOTE_TTL_HOURS,
                    "vote_threshold": VOTE_THRESHOLD,
                    "valid_statuses": sorted(VALID_STATUSES),
                }
            )
        if route_path == "/api/markets":
            return self.handle_get_markets()
        if route_path == "/api/admin/markets":
            return self.handle_get_admin_markets()

        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self):
        route_path = urlsplit(self.path).path
        if route_path == "/api/vote":
            return self.handle_post_vote()
        if route_path == "/api/overview/markets":
            return self.handle_post_overview_markets()
        self.send_error(HTTPStatus.NOT_FOUND)

    def handle_get_markets(self):
        conn = sqlite3.connect(DB_FILE)
        try:
            cleanup_expired_votes(conn)
            conn.commit()

            markets = query_all_markets(conn)
            payload = build_markets_payload(conn, markets, include_details=False, include_only_valid=False)
            self._send_json(payload)
        finally:
            conn.close()

    def handle_post_overview_markets(self):
        try:
            data = self._read_json() or {}
        except json.JSONDecodeError:
            return self._send_json({"error": "Invalid JSON"}, status=HTTPStatus.BAD_REQUEST)

        lat = data.get("lat")
        lon = data.get("lon")
        include_all = bool(data.get("include_all", False))

        if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
            return self._send_json({"error": "lat/lon required"}, status=HTTPStatus.BAD_REQUEST)

        city = city_from_center(float(lat), float(lon), self.state.spatial_index)

        conn = sqlite3.connect(DB_FILE)
        try:
            cleanup_expired_votes(conn)
            conn.commit()

            markets = query_markets_by_city(conn, city)
            nearby_cities = get_nearby_cities_for_city(self.state.spatial_index, city)
            payload = build_markets_payload(
                conn,
                markets,
                include_details=True,
                include_only_valid=(not include_all),
            )
            self._send_json(
                {
                    "city": city,
                    "nearby_cities": nearby_cities,
                    "generated_at": utc_now().isoformat(),
                    "has_valid_data": len(payload) > 0,
                    "include_all": include_all,
                    "markets": payload,
                }
            )
        finally:
            conn.close()

    def handle_post_vote(self):
        try:
            data = self._read_json()
        except json.JSONDecodeError:
            return self._send_json({"error": "Invalid JSON"}, status=HTTPStatus.BAD_REQUEST)

        if not isinstance(data, dict):
            return self._send_json({"error": "Invalid payload"}, status=HTTPStatus.BAD_REQUEST)

        market_id = data.get("market_id")
        status = data.get("status")
        if not isinstance(market_id, int) or market_id not in self.state.market_by_id:
            return self._send_json({"error": "Invalid market_id"}, status=HTTPStatus.BAD_REQUEST)
        if status not in VALID_STATUSES:
            return self._send_json({"error": "Invalid status"}, status=HTTPStatus.BAD_REQUEST)

        ip = self.client_address[0]
        now_iso = utc_now().isoformat()
        cutoff = (utc_now() - timedelta(hours=SAME_STATUS_COOLDOWN_HOURS)).isoformat()
        market = self.state.market_by_id[market_id]

        conn = sqlite3.connect(DB_FILE)
        try:
            cleanup_expired_votes(conn)

            cursor = conn.execute(
                """
                SELECT COUNT(*)
                FROM votes
                WHERE market_id = ? AND ip = ? AND status = ? AND created_at >= ?
                """,
                (market_id, ip, status, cutoff),
            )
            existing = cursor.fetchone()[0]

            accepted = 0 if existing > 0 else 1
            conn.execute(
                """
                INSERT INTO vote_events (market_id, market_address, status, ip, created_at, accepted)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (market_id, market["address"], status, ip, now_iso, accepted),
            )

            if existing > 0:
                conn.commit()
                return self._send_json(
                    {
                        "error": "duplicate_vote_same_status",
                        "message": f"This IP has already voted this status for this market within {SAME_STATUS_COOLDOWN_HOURS} hour.",
                    },
                    status=HTTPStatus.CONFLICT,
                )

            conn.execute(
                "INSERT INTO votes (market_id, ip, status, created_at) VALUES (?, ?, ?, ?)",
                (market_id, ip, status, now_iso),
            )
            conn.commit()

            one_market = [market]
            payload = build_markets_payload(conn, one_market, include_details=False, include_only_valid=False)
            self._send_json({"ok": True, "market": payload[0]})
        finally:
            conn.close()

    def handle_get_admin_markets(self):
        conn = sqlite3.connect(DB_FILE)
        try:
            cleanup_expired_votes(conn)
            conn.commit()

            markets = query_all_markets(conn)
            payload = build_markets_payload(conn, markets, include_details=True, include_only_valid=False)
            self._send_json(
                {
                    "generated_at": utc_now().isoformat(),
                    "vote_ttl_hours": VOTE_TTL_HOURS,
                    "vote_threshold": VOTE_THRESHOLD,
                    "markets": payload,
                }
            )
        finally:
            conn.close()


def main():
    if not SUPERMARKETS_FILE.exists():
        raise FileNotFoundError("Supermarkets.txt not found")
    if not GEOCODE_CACHE_FILE.exists():
        print("Geocode cache not found. Please run: python geocode_builder.py")
        return

    cache = load_geocode_cache(GEOCODE_CACHE_FILE)
    markets = parse_supermarkets(SUPERMARKETS_FILE)
    markets = enrich_with_coordinates(markets, cache)
    spatial_index = get_spatial_index(cache)

    missing_geo = [m for m in markets if m["lat"] is None or m["lon"] is None]
    if missing_geo:
        print(f"Warning: {len(missing_geo)} markets have missing coordinates.")
        print("Please run: python geocode_builder.py to fill in missing geocodes.")

    init_db()
    sync_markets_to_db(markets)

    state = AppState(markets, spatial_index)
    Handler.state = state

    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Serving Find L Eggs at http://{HOST}:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
