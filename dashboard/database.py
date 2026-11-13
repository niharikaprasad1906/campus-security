import sqlite3
from datetime import datetime
from pathlib import Path

import pandas as pd


INCIDENT_SELECT_COLUMNS = """
    id, timestamp, incident_type, camera_id, camera_name, zone_name,
    track_id, extra_info
"""


def _incident_review_columns(connection: sqlite3.Connection) -> tuple[str, str]:
    existing_columns = {
        row[1] for row in connection.execute("PRAGMA table_info(incidents)")
    }
    review_status = (
        "review_status"
        if "review_status" in existing_columns
        else "'Pending' AS review_status"
    )
    reviewed_at = (
        "reviewed_at"
        if "reviewed_at" in existing_columns
        else "NULL AS reviewed_at"
    )
    return review_status, reviewed_at


def load_incidents(database_path: Path) -> pd.DataFrame:
    if not database_path.is_file():
        raise FileNotFoundError(f"Incident database not found: {database_path}")

    database_uri = f"{database_path.resolve().as_uri()}?mode=ro"
    connection = sqlite3.connect(database_uri, uri=True)
    try:
        review_status, reviewed_at = _incident_review_columns(connection)
        return pd.read_sql_query(
            f"""
            SELECT {INCIDENT_SELECT_COLUMNS}, {review_status}, {reviewed_at}
            FROM incidents
            ORDER BY timestamp DESC, id DESC
            """,
            connection,
        )
    finally:
        connection.close()


def latest_incident_id(database_path: Path) -> int:
    if not database_path.is_file():
        raise FileNotFoundError(f"Incident database not found: {database_path}")

    database_uri = f"{database_path.resolve().as_uri()}?mode=ro"
    connection = sqlite3.connect(database_uri, uri=True)
    try:
        return int(
            connection.execute(
                "SELECT COALESCE(MAX(id), 0) FROM incidents"
            ).fetchone()[0]
        )
    finally:
        connection.close()


def load_incidents_after(
    database_path: Path, incident_id: int, camera_id: str
) -> pd.DataFrame:
    if not database_path.is_file():
        raise FileNotFoundError(f"Incident database not found: {database_path}")

    database_uri = f"{database_path.resolve().as_uri()}?mode=ro"
    connection = sqlite3.connect(database_uri, uri=True)
    try:
        review_status, reviewed_at = _incident_review_columns(connection)
        return pd.read_sql_query(
            f"""
            SELECT {INCIDENT_SELECT_COLUMNS}, {review_status}, {reviewed_at}
            FROM incidents
            WHERE id > ? AND camera_id = ?
            ORDER BY id
            """,
            connection,
            params=(incident_id, camera_id),
        )
    finally:
        connection.close()


def mark_incident_reviewed(database_path: Path, incident_id: int) -> bool:
    if not database_path.is_file():
        raise FileNotFoundError(f"Incident database not found: {database_path}")

    connection = sqlite3.connect(database_path)
    try:
        with connection:
            existing_columns = {
                row[1] for row in connection.execute("PRAGMA table_info(incidents)")
            }
            if "review_status" not in existing_columns:
                connection.execute(
                    "ALTER TABLE incidents ADD COLUMN review_status "
                    "TEXT NOT NULL DEFAULT 'Pending'"
                )
            if "reviewed_at" not in existing_columns:
                connection.execute(
                    "ALTER TABLE incidents ADD COLUMN reviewed_at TEXT"
                )
            cursor = connection.execute(
                """
                UPDATE incidents
                SET review_status = 'Reviewed', reviewed_at = ?
                WHERE id = ? AND COALESCE(review_status, 'Pending') != 'Reviewed'
                """,
                (datetime.now().isoformat(timespec="seconds"), incident_id),
            )
            return cursor.rowcount == 1
    finally:
        connection.close()
