from datetime import datetime
from pathlib import Path

import pandas as pd

from dashboard import storage


INCIDENT_SELECT_COLUMNS = """
    id, timestamp, incident_type, camera_id, camera_name, zone_name,
    track_id, extra_info
"""


def _incident_review_columns(connection) -> tuple[str, str]:
    if storage.is_supabase_configured():
        cursor = storage.execute(
            connection,
            "",
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = current_schema() AND table_name = 'incidents'
            """,
        )
        existing_columns = {row[0] for row in cursor.fetchall()}
    else:
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


def _read_dataframe(
    connection,
    sqlite_query: str,
    postgres_query: str,
    parameters: tuple = (),
) -> pd.DataFrame:
    cursor = storage.execute(connection, sqlite_query, postgres_query, parameters)
    rows = cursor.fetchall()
    columns = [
        column.name if hasattr(column, "name") else column[0]
        for column in cursor.description
    ]
    return pd.DataFrame.from_records(rows, columns=columns)


def _connect(database_path: Path, readonly: bool = True):
    if not storage.is_supabase_configured() and not database_path.is_file():
        raise FileNotFoundError(f"Incident database not found: {database_path}")
    return storage.connect(database_path, readonly=readonly)


def load_incidents(database_path: Path) -> pd.DataFrame:
    connection = _connect(database_path)
    try:
        review_status, reviewed_at = _incident_review_columns(connection)
        query = f"""
            SELECT {INCIDENT_SELECT_COLUMNS}, {review_status}, {reviewed_at}
            FROM incidents
            ORDER BY timestamp DESC, id DESC
        """
        return _read_dataframe(connection, query, query)
    finally:
        connection.close()


def latest_incident_id(database_path: Path) -> int:
    connection = _connect(database_path)
    try:
        query = "SELECT COALESCE(MAX(id), 0) FROM incidents"
        cursor = storage.execute(connection, query, query)
        row = cursor.fetchone()
        if row is None:
            raise storage.StorageError("Incident database query returned no result.")
        return int(row[0])
    finally:
        connection.close()


def load_incidents_after(
    database_path: Path, incident_id: int, camera_id: str
) -> pd.DataFrame:
    connection = _connect(database_path)
    try:
        review_status, reviewed_at = _incident_review_columns(connection)
        select = f"""
            SELECT {INCIDENT_SELECT_COLUMNS}, {review_status}, {reviewed_at}
            FROM incidents
            WHERE id > ? AND camera_id = ?
            ORDER BY id
        """
        postgres_select = f"""
            SELECT {INCIDENT_SELECT_COLUMNS}, {review_status}, {reviewed_at}
            FROM incidents
            WHERE id > %s AND camera_id = %s
            ORDER BY id
        """
        return _read_dataframe(
            connection,
            select,
            postgres_select,
            (incident_id, camera_id),
        )
    finally:
        connection.close()


def mark_incident_reviewed(database_path: Path, incident_id: int) -> bool:
    connection = _connect(database_path, readonly=False)
    try:
        if storage.is_supabase_configured():
            storage.execute(
                connection,
                "",
                "ALTER TABLE incidents ADD COLUMN IF NOT EXISTS "
                "review_status TEXT NOT NULL DEFAULT 'Pending'",
            )
            storage.execute(
                connection,
                "",
                "ALTER TABLE incidents ADD COLUMN IF NOT EXISTS reviewed_at TEXT",
            )
        else:
            existing_columns = {
                row[1] for row in connection.execute("PRAGMA table_info(incidents)")
            }
            if "review_status" not in existing_columns:
                storage.execute(
                    connection,
                    "ALTER TABLE incidents ADD COLUMN review_status "
                    "TEXT NOT NULL DEFAULT 'Pending'",
                    "",
                )
            if "reviewed_at" not in existing_columns:
                storage.execute(
                    connection,
                    "ALTER TABLE incidents ADD COLUMN reviewed_at TEXT",
                    "",
                )

        update = """
            UPDATE incidents
            SET review_status = 'Reviewed', reviewed_at = ?
            WHERE id = ? AND COALESCE(review_status, 'Pending') != 'Reviewed'
        """
        postgres_update = """
            UPDATE incidents
            SET review_status = 'Reviewed', reviewed_at = %s
            WHERE id = %s AND COALESCE(review_status, 'Pending') != 'Reviewed'
        """
        cursor = storage.execute(
            connection,
            update,
            postgres_update,
            (datetime.now().isoformat(timespec="seconds"), incident_id),
        )
        storage.commit(connection)
        return cursor.rowcount == 1
    finally:
        connection.close()
