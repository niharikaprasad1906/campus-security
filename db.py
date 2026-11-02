"""
db.py — Incident logging for Campus Security system.

Stores incidents in SQLite (incidents.db) for structured querying and also
appends a human-readable line to incident_log.txt for backward compatibility.

Deduplication: an identical (incident_type, camera_id, zone_name, track_id)
combination logged within DEDUP_WINDOW_SECONDS is silently dropped so the
same physical event is not recorded on every frame.
"""

import sqlite3
import datetime
import os

DB_PATH = "incidents.db"
TEXT_LOG_PATH = "incident_log.txt"

# Identical events within this window (seconds) are considered duplicates.
DEDUP_WINDOW_SECONDS = 10


def init_db():
    """
    Create the incidents table if it does not already exist.
    Safe to call on every startup — does not delete existing data.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS incidents (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp     TEXT    NOT NULL,
            incident_type TEXT    NOT NULL,
            camera_id     TEXT    NOT NULL,
            camera_name   TEXT    NOT NULL,
            zone_name     TEXT    NOT NULL DEFAULT '',
            track_id      TEXT,
            extra_info    TEXT
        )
        """
    )
    conn.commit()
    conn.close()


def _is_duplicate(cursor, incident_type, camera_id, zone_name, track_id):
    """
    Return True if an identical event was already recorded within
    DEDUP_WINDOW_SECONDS.
    """
    cutoff = (
        datetime.datetime.now() - datetime.timedelta(seconds=DEDUP_WINDOW_SECONDS)
    ).strftime("%Y-%m-%d %H:%M:%S")

    cursor.execute(
        """
        SELECT id FROM incidents
        WHERE incident_type = ?
          AND camera_id     = ?
          AND zone_name     = ?
          AND track_id      IS ?
          AND timestamp     >= ?
        LIMIT 1
        """,
        (incident_type, camera_id, zone_name, track_id, cutoff),
    )
    return cursor.fetchone() is not None


def log_incident(
    incident_type,
    camera_id="cam_01",
    camera_name="Main Gate",
    zone_name="",
    track_id=None,
    extra_info=None,
):
    """
    Log an incident to incidents.db and incident_log.txt.

    Parameters
    ----------
    incident_type : str
        Human-readable event name, e.g. 'Restricted Zone Intrusion'.
    camera_id : str
        Unique machine-readable camera identifier.
    camera_name : str
        Human-readable camera label.
    zone_name : str
        Name of the zone where the event occurred.
    track_id : int | str | None
        Tracker-assigned person ID (may be None if not available).
    extra_info : str | None
        Optional free-text detail appended to the record.
    """
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    track_id_str = str(track_id) if track_id is not None else None

    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        if _is_duplicate(cursor, incident_type, camera_id, zone_name, track_id_str):
            conn.close()
            return  # Silent dedup — do not write anything

        cursor.execute(
            """
            INSERT INTO incidents
                (timestamp, incident_type, camera_id, camera_name,
                 zone_name, track_id, extra_info)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                timestamp,
                incident_type,
                camera_id,
                camera_name,
                zone_name,
                track_id_str,
                extra_info,
            ),
        )
        conn.commit()
        conn.close()
    except sqlite3.Error as e:
        print(f"[DB ERROR] Could not log incident: {e}")

    # Also write to the legacy text log for backward compatibility.
    try:
        with open(TEXT_LOG_PATH, "a") as f:
            id_part = f"Person ID: {track_id}" if track_id is not None else "Person ID: N/A"
            zone_part = f" | Zone: {zone_name}" if zone_name else ""
            extra_part = f" | {extra_info}" if extra_info else ""
            f.write(
                f"{timestamp} | {incident_type} | {id_part}"
                f" | Camera: {camera_name}{zone_part}{extra_part}\n"
            )
    except OSError as e:
        print(f"[LOG ERROR] Could not write to text log: {e}")


def get_recent_incidents(limit=50):
    """
    Return the most recent incidents as a list of dicts.
    Useful for a dashboard or debugging.
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM incidents ORDER BY timestamp DESC LIMIT ?", (limit,)
        )
        rows = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return rows
    except sqlite3.Error as e:
        print(f"[DB ERROR] Could not read incidents: {e}")
        return []
