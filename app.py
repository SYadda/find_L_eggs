#!/usr/bin/env python3
import json
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
VOTE_TTL_HOURS = 3
VOTE_THRESHOLD = 3

VALID_STATUSES = {"plenty", "few", "none"}

CITY_BY_ADDRESS_PATTERN = [
    (re.compile(r"\bErlangen\b", re.IGNORECASE), "Erlangen"),
    (re.compile(r"\bFürth\b", re.IGNORECASE), "Fürth"),
    (re.compile(r"\bNürnberg\b", re.IGNORECASE), "Nürnberg"),
]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def detect_city(address: str) -> str:
    for pattern, city_name in CITY_BY_ADDRESS_PATTERN:
        if pattern.search(address):
            return city_name
    return "Unknown"


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
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_geocode_cache(path: Path, cache):
    with path.open("w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def enrich_with_coordinates(markets):
    """
    从缓存中应用地理编码坐标到市场数据。
    缓存的生成和更新由 geocode_builder.py 脚本独立处理。
    """
    cache = load_geocode_cache(GEOCODE_CACHE_FILE)

    for market in markets:
        key = market["query"]
        geo = cache.get(key)
        market["lat"] = geo["lat"] if geo else None
        market["lon"] = geo["lon"] if geo else None

    return markets


def init_db():
    conn = sqlite3.connect(DB_FILE)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS votes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            market_id INTEGER NOT NULL,
            ip TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()


def cleanup_expired_votes(conn):
    cutoff = (utc_now() - timedelta(hours=VOTE_TTL_HOURS)).isoformat()
    conn.execute("DELETE FROM votes WHERE created_at < ?", (cutoff,))


def vote_counts_for_market(conn, market_id):
    cutoff = (utc_now() - timedelta(hours=VOTE_TTL_HOURS)).isoformat()
    cursor = conn.execute(
        """
        SELECT status, COUNT(*)
        FROM votes
        WHERE market_id = ? AND created_at >= ?
        GROUP BY status
        """,
        (market_id, cutoff),
    )
    counts = {"plenty": 0, "few": 0, "none": 0}
    for status, count in cursor.fetchall():
        counts[status] = count
    return counts


def vote_details_for_market(conn, market_id):
    cutoff_dt = utc_now() - timedelta(hours=VOTE_TTL_HOURS)
    cutoff = cutoff_dt.isoformat()
    cursor = conn.execute(
        """
        SELECT id, status, created_at
        FROM votes
        WHERE market_id = ? AND created_at >= ?
        ORDER BY created_at ASC
        """,
        (market_id, cutoff),
    )

    details = []
    now = utc_now()
    for vote_id, status, created_at_str in cursor.fetchall():
        created_at = datetime.fromisoformat(created_at_str)
        expires_at = created_at + timedelta(hours=VOTE_TTL_HOURS)
        remaining_seconds = int((expires_at - now).total_seconds())
        if remaining_seconds < 0:
            continue
        details.append(
            {
                "vote_id": vote_id,
                "status": status,
                "created_at": created_at.isoformat(),
                "expires_at": expires_at.isoformat(),
                "remaining_seconds": remaining_seconds,
            }
        )
    return details


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
    return winning_status


def market_payload(market, counts, vote_details):
    payload = {
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
    return payload


class AppState:
    def __init__(self, markets):
        self.markets = markets
        self.market_by_id = {m["id"]: m for m in markets}


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
        self.send_error(HTTPStatus.NOT_FOUND)

    def handle_get_markets(self):
        conn = sqlite3.connect(DB_FILE)
        try:
            cleanup_expired_votes(conn)
            conn.commit()

            payload = []
            for market in self.state.markets:
                counts = vote_counts_for_market(conn, market["id"])
                vote_details = vote_details_for_market(conn, market["id"])
                payload.append(market_payload(market, counts, vote_details))
            self._send_json(payload)
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
        cutoff = (utc_now() - timedelta(hours=VOTE_TTL_HOURS)).isoformat()

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
            if existing > 0:
                conn.commit()
                return self._send_json(
                    {
                        "error": "duplicate_vote_same_status",
                        "message": "This IP has already voted this status for this market within 3 hours.",
                    },
                    status=HTTPStatus.CONFLICT,
                )

            conn.execute(
                "INSERT INTO votes (market_id, ip, status, created_at) VALUES (?, ?, ?, ?)",
                (market_id, ip, status, utc_now().isoformat()),
            )
            conn.commit()

            counts = vote_counts_for_market(conn, market_id)
            vote_details = vote_details_for_market(conn, market_id)
            market = self.state.market_by_id[market_id]
            self._send_json({"ok": True, "market": market_payload(market, counts, vote_details)})
        finally:
            conn.close()

    def handle_get_admin_markets(self):
        conn = sqlite3.connect(DB_FILE)
        try:
            cleanup_expired_votes(conn)
            conn.commit()

            payload = []
            for market in self.state.markets:
                counts = vote_counts_for_market(conn, market["id"])
                vote_details = vote_details_for_market(conn, market["id"])
                payload.append(
                    {
                        **market_payload(market, counts, vote_details),
                        "total_votes": len(vote_details),
                        "vote_details": vote_details,
                    }
                )

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

    # Check if geocode cache exists and needs updating
    if not GEOCODE_CACHE_FILE.exists():
        print("Geocode cache not found. Please run: python geocode_builder.py")
        print("This will build the initial cache for all addresses.")
        return

    markets = parse_supermarkets(SUPERMARKETS_FILE)
    markets = enrich_with_coordinates(markets)
    
    # Check if any markets lack coordinates (all should have been encoded)
    missing_geo = [m for m in markets if m["lat"] is None or m["lon"] is None]
    if missing_geo:
        print(f"Warning: {len(missing_geo)} markets have missing coordinates.")
        print("Please run: python geocode_builder.py")
        print("to fill in the missing geocodes.")

    init_db()

    state = AppState(markets)
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
