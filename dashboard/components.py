from datetime import date

import pandas as pd
import streamlit as st

from dashboard.timezone import current_time


INCIDENT_LABELS = {
    "Restricted Zone Intrusion": "Intrusion",
    "Overcrowding Detected": "Overcrowding",
    "Loitering Detected": "Loitering",
    "After-Hours Movement": "After-hours",
}
SEVERITY_BY_TYPE = {
    "Restricted Zone Intrusion": "Critical",
    "Overcrowding Detected": "High",
    "Loitering Detected": "Medium",
    "After-Hours Movement": "Medium",
}
SEVERITY_COLORS = {
    "Critical": "#ff6577",
    "High": "#ffad5c",
    "Medium": "#f3cb62",
    "Informational": "#b69aff",
}


def with_derived_fields(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    result["timestamp"] = pd.to_datetime(result["timestamp"], errors="coerce")
    result["severity"] = result["incident_type"].map(SEVERITY_BY_TYPE).fillna(
        "Informational"
    )
    if "review_status" not in result.columns:
        result["review_status"] = "Pending"
    result["review_status"] = result["review_status"].fillna("Pending")
    if "reviewed_at" not in result.columns:
        result["reviewed_at"] = None
    return result


def date_filter(
    frame: pd.DataFrame, start_date: date, end_date: date
) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    timestamps = pd.to_datetime(frame["timestamp"], errors="coerce")
    start = pd.Timestamp(start_date)
    end = pd.Timestamp(end_date) + pd.Timedelta(days=1) - pd.Timedelta(microseconds=1)
    return frame.loc[timestamps.between(start, end)].copy()


def incident_type_options(frame: pd.DataFrame) -> list[str]:
    return sorted(frame["incident_type"].dropna().unique().tolist())


def camera_options(frame: pd.DataFrame) -> list[str]:
    return sorted(frame["camera_name"].dropna().unique().tolist())


def date_bounds(frame: pd.DataFrame) -> tuple[date, date]:
    timestamps = pd.to_datetime(frame["timestamp"], errors="coerce").dropna()
    if timestamps.empty:
        today = current_time().date()
        return today, today
    return timestamps.min().date(), timestamps.max().date()


def metric_row(
    frame: pd.DataFrame, configured_camera_count: int | None = None
) -> None:
    top_row = st.columns(4)
    top_row[0].metric("Total incidents", len(frame))
    for column, (incident_type, label) in zip(top_row[1:], list(INCIDENT_LABELS.items())[:3]):
        column.metric(label, int(frame["incident_type"].eq(incident_type).sum()))

    bottom_row = st.columns(3)
    bottom_row[0].metric(
        "After-hours",
        int(frame["incident_type"].eq("After-Hours Movement").sum()),
    )
    if configured_camera_count is not None:
        bottom_row[1].metric("Configured cameras", configured_camera_count)
        bottom_row[2].metric(
            "Pending review", int(frame["review_status"].eq("Pending").sum())
        )
    else:
        bottom_row[1].metric(
            "Pending review", int(frame["review_status"].eq("Pending").sum())
        )
        bottom_row[2].metric(
            "Reviewed", int(frame["review_status"].eq("Reviewed").sum())
        )
    st.caption(
        "No previous-period comparisons shown because the available history "
        "does not establish a comparable reporting period."
    )
