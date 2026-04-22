#!/usr/bin/env python3
import sqlite3
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DB_FILE = BASE_DIR / "votes.db"


def main():
    if not DB_FILE.exists():
        print(f"Database not found: {DB_FILE}")
        return

    conn = sqlite3.connect(DB_FILE)
    try:
        cursor = conn.execute("SELECT COUNT(*) FROM votes")
        before_count = cursor.fetchone()[0]

        conn.execute("DELETE FROM votes")
        conn.execute("DELETE FROM sqlite_sequence WHERE name = 'votes'")
        conn.commit()
    finally:
        conn.close()

    print(f"Reset complete. Deleted {before_count} rows from votes.")


if __name__ == "__main__":
    main()