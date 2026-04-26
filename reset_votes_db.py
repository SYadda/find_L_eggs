#!/usr/bin/env python3
import sqlite3
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DB_FILE = BASE_DIR / "votes.db"


def table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    cursor = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    )
    return cursor.fetchone() is not None


def get_count(conn: sqlite3.Connection, table_name: str) -> int:
    cursor = conn.execute(f"SELECT COUNT(*) FROM {table_name}")
    return int(cursor.fetchone()[0])


def main():
    if not DB_FILE.exists():
        print(f"Database not found: {DB_FILE}")
        return

    conn = sqlite3.connect(DB_FILE)
    try:
        votes_exists = table_exists(conn, "votes")
        events_exists = table_exists(conn, "vote_events")
        sequence_exists = table_exists(conn, "sqlite_sequence")

        votes_before = get_count(conn, "votes") if votes_exists else 0
        events_before = get_count(conn, "vote_events") if events_exists else 0

        if votes_exists:
            conn.execute("DELETE FROM votes")
        if events_exists:
            conn.execute("DELETE FROM vote_events")

        if sequence_exists:
            if votes_exists:
                conn.execute("DELETE FROM sqlite_sequence WHERE name = 'votes'")
            if events_exists:
                conn.execute("DELETE FROM sqlite_sequence WHERE name = 'vote_events'")

        conn.commit()
    finally:
        conn.close()

    if not votes_exists and not events_exists:
        print("No vote tables found. Nothing to reset.")
        return

    print(
        "Reset complete. "
        f"Deleted {votes_before} rows from votes and {events_before} rows from vote_events."
    )


if __name__ == "__main__":
    main()