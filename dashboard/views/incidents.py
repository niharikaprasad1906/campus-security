import re
import sqlite3
from pathlib import Path
from typing import Callable

import pandas as pd
import streamlit as st

from dashboard.database import mark_incident_reviewed
from dashboard.components import (
    camera_options,
    date_bounds,
    date_filter,
    incident_type_options,
    with_derived_fields,
)


def render(
    frame: pd.DataFrame,
    database_path: Path,
    refresh_incidents: Callable[[], None],
) -> None:
    st.caption(
        "Search and filter the incident history. Severity is derived from incident "
        "type for display. Review statuses are persisted in SQLite."
    )
    enriched = with_derived_fields(frame)
    if enriched.empty:
        st.info("No incidents are available to review.")
        return

    today = pd.Timestamp.today().date()
    today_count = int(enriched["timestamp"].dt.date.eq(today).sum())
    critical_count = int(enriched["severity"].eq("Critical").sum())
    (
        total_column,
        critical_column,
        today_column,
        pending_column,
        reviewed_column,
    ) = st.columns(5)
    total_column.metric("Total incidents", len(enriched))
    critical_column.metric("Critical incidents", critical_count)
    today_column.metric("Incidents today", today_count)
    pending_column.metric(
        "Pending review", int(enriched["review_status"].eq("Pending").sum())
    )
    reviewed_column.metric(
        "Reviewed", int(enriched["review_status"].eq("Reviewed").sum())
    )

    with st.expander("Filters and search", expanded=True):
        search_column, type_column, camera_column = st.columns([1.5, 1, 1])
        query = search_column.text_input(
            "Search ID, camera, incident, or person ID", key="incident_search"
        )
        selected_types = type_column.multiselect(
            "Incident type",
            incident_type_options(enriched),
            key="incident_types",
        )
        selected_cameras = camera_column.multiselect(
            "Camera", camera_options(enriched), key="incident_cameras"
        )

        severity_column, status_column, dates_column = st.columns([1, 1, 2])
        selected_severities = severity_column.multiselect(
            "Derived severity",
            sorted(enriched["severity"].unique()),
            key="incident_severities",
        )
        selected_statuses = status_column.multiselect(
            "Review status",
            ["Pending", "Reviewed"],
            key="incident_review_statuses",
        )
        minimum_date, maximum_date = date_bounds(enriched)
        date_range = dates_column.date_input(
            "Date range",
            value=(minimum_date, maximum_date),
            min_value=minimum_date,
            max_value=maximum_date,
            key="incident_date_range",
        )

    filtered = enriched.copy()
    if selected_types:
        filtered = filtered[filtered["incident_type"].isin(selected_types)]
    if selected_cameras:
        filtered = filtered[filtered["camera_name"].isin(selected_cameras)]
    if selected_severities:
        filtered = filtered[filtered["severity"].isin(selected_severities)]
    if selected_statuses:
        filtered = filtered[filtered["review_status"].isin(selected_statuses)]
    if query.strip():
        search = re.escape(query.strip())
        searchable = filtered[
            ["id", "camera_id", "camera_name", "incident_type", "track_id"]
        ].fillna("").astype(str)
        filtered = filtered[
            searchable.apply(
                lambda column: column.str.contains(
                    search, case=False, regex=True
                )
            ).any(axis=1)
        ]
    if len(date_range) == 2:
        filtered = date_filter(filtered, date_range[0], date_range[1])
    else:
        st.warning("Select both a start and end date.")
        return

    display = filtered.rename(
        columns={
            "id": "Incident ID",
            "timestamp": "Timestamp",
            "incident_type": "Incident type",
            "camera_name": "Camera",
            "zone_name": "Zone",
            "track_id": "Person ID",
            "severity": "Derived severity",
            "review_status": "Review status",
            "reviewed_at": "Reviewed at",
        }
    )
    st.markdown(f"**{len(filtered)}** matching incidents")
    st.dataframe(
        display[
            [
                "Incident ID",
                "Timestamp",
                "Incident type",
                "Camera",
                "Zone",
                "Person ID",
                "Derived severity",
                "Review status",
                "Reviewed at",
            ]
        ].fillna("—"),
        hide_index=True,
        width="stretch",
    )

    if not filtered.empty:
        csv_data = display.to_csv(index=False).encode("utf-8")
        st.download_button(
            "Download filtered incidents (CSV)",
            data=csv_data,
            file_name="campus-security-incidents.csv",
            mime="text/csv",
        )
        record_ids = filtered["id"].astype(int).tolist()
        selected_id = st.selectbox(
            "Incident details",
            record_ids,
            format_func=lambda incident_id: (
                f"#{incident_id} · "
                f"{filtered.loc[filtered['id'].eq(incident_id), 'incident_type'].iloc[0]}"
            ),
        )
        record = filtered.loc[filtered["id"].eq(selected_id)].iloc[0]
        with st.expander(f"Incident #{selected_id} details", expanded=True):
            details_left, details_right = st.columns(2)
            zone_name = record["zone_name"]
            track_id = record["track_id"]
            reviewed_at = record["reviewed_at"]
            extra_info = record["extra_info"]
            zone_display = (
                str(zone_name)
                if pd.notna(zone_name) and str(zone_name).strip()
                else "Not specified"
            )
            track_display = (
                str(track_id) if pd.notna(track_id) else "Not available"
            )
            reviewed_display = (
                str(reviewed_at) if pd.notna(reviewed_at) else "—"
            )
            extra_display = (
                str(extra_info)
                if pd.notna(extra_info) and str(extra_info).strip()
                else "None recorded"
            )
            details_left.write(f"**Timestamp:** {record['timestamp']}")
            details_left.write(f"**Camera:** {record['camera_name']} ({record['camera_id']})")
            details_left.write(f"**Zone:** {zone_display}")
            details_right.write(f"**Incident:** {record['incident_type']}")
            details_right.write(f"**Person/track ID:** {track_display}")
            details_right.write(
                f"**Derived severity:** {record['severity']} "
                "(not stored in the database)"
            )
            details_right.write(
                f"**Review status:** {record['review_status']}"
            )
            details_right.write(f"**Reviewed at:** {reviewed_display}")
            st.write(f"**Additional information:** {extra_display}")
            if record["review_status"] != "Reviewed":
                if st.button(
                    "Mark as reviewed",
                    key=f"review_incident_{selected_id}",
                    type="primary",
                ):
                    try:
                        updated = mark_incident_reviewed(database_path, int(selected_id))
                    except (OSError, sqlite3.Error) as error:
                        st.error(f"Could not save incident review status: {error}")
                    else:
                        if not updated:
                            st.warning("The incident was already reviewed or no longer exists.")
                        else:
                            refresh_incidents()
                            st.rerun()
