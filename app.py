#!/usr/bin/env python3
import json
import os
import re
import sqlite3
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
SUPERMARKETS_FILE = BASE_DIR / "Supermarkets.txt"
GEOCODE_CACHE_FILE = BASE_DIR / "geocode_cache.json"
DB_FILE = BASE_DIR / "votes.db"

HOST = "127.0.0.1"
PORT = 8000
VOTE_TTL_HOURS = 3
VOTE_THRESHOLD = 3

VALID_STATUSES = {"plenty", "few", "none"}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


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

            city = "Erlangen"
            zip_code_match = re.search(r"\b(91052|91054|91056|91058)\b", line)
            zip_code = zip_code_match.group(1) if zip_code_match else ""
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


def geocode_address(query: str):
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

    with urllib.request.urlopen(request, timeout=20) as response:
        data = json.loads(response.read().decode("utf-8"))
        if not data:
            return None
        first = data[0]
        return {
            "lat": float(first["lat"]),
            "lon": float(first["lon"]),
        }


def enrich_with_coordinates(markets):
    cache = load_geocode_cache(GEOCODE_CACHE_FILE)
    changed = False

    for market in markets:
        key = market["query"]
        if key not in cache:
            try:
                result = geocode_address(key)
            except Exception:
                result = None
            cache[key] = result
            changed = True
            # Respect Nominatim usage policy and avoid burst requests.
            time.sleep(1.05)

        geo = cache.get(key)
        market["lat"] = geo["lat"] if geo else None
        market["lon"] = geo["lon"] if geo else None

    if changed:
        save_geocode_cache(GEOCODE_CACHE_FILE, cache)

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


def determine_display_status(counts):
    max_votes = max(counts.values())
    if max_votes < VOTE_THRESHOLD:
        return "unknown"

    top_statuses = [k for k, v in counts.items() if v == max_votes]
    if len(top_statuses) != 1:
        return "unknown"
    return top_statuses[0]


def market_payload(market, counts):
    payload = {
        "id": market["id"],
        "brand": market["brand"],
        "address": market["address"],
        "zip": market["zip"],
        "lat": market["lat"],
        "lon": market["lon"],
        "counts": counts,
        "display_status": determine_display_status(counts),
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
        if self.path == "/" or self.path == "/index.html":
            return self._send_file(BASE_DIR / "index.html", "text/html; charset=utf-8")
        if self.path == "/admin" or self.path == "/admin.html":
            return self._send_file(BASE_DIR / "admin.html", "text/html; charset=utf-8")
        if self.path == "/styles.css":
            return self._send_file(BASE_DIR / "styles.css", "text/css; charset=utf-8")
        if self.path == "/app.js":
            return self._send_file(BASE_DIR / "app.js", "application/javascript; charset=utf-8")
        if self.path == "/admin.js":
            return self._send_file(BASE_DIR / "admin.js", "application/javascript; charset=utf-8")
        if self.path == "/api/config":
            return self._send_json(
                {
                    "vote_ttl_hours": VOTE_TTL_HOURS,
                    "vote_threshold": VOTE_THRESHOLD,
                    "valid_statuses": sorted(VALID_STATUSES),
                }
            )
        if self.path == "/api/markets":
            return self.handle_get_markets()
        if self.path == "/api/admin/markets":
            return self.handle_get_admin_markets()

        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self):
        if self.path == "/api/vote":
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
                payload.append(market_payload(market, counts))
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
            market = self.state.market_by_id[market_id]
            self._send_json({"ok": True, "market": market_payload(market, counts)})
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
                        **market_payload(market, counts),
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

    markets = parse_supermarkets(SUPERMARKETS_FILE)
    markets = enrich_with_coordinates(markets)
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
