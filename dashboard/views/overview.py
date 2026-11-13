from datetime import date
from pathlib import Path
from typing import Callable

import pandas as pd
import streamlit as st

from cameras import ACTIVE_CAMERAS
from dashboard.charts import daily_trend_chart, distribution_chart
from dashboard.components import metric_row


ROOT_PATH = Path(__file__).resolve().parents[2]


def _camera_status(camera: object) -> str:
    recording = ROOT_PATH / camera.video_path
    if recording.is_file():
        return "Recorded sample available · no live connection"
    return "No connected feed or available recording"


def render(frame: pd.DataFrame, navigate_to: Callable[[str], None]) -> None:
    st.caption(
        "Monitoring view based on records in the incident database. "
        "The dashboard does not start or control the detection backend."
    )
    metric_row(frame, configured_camera_count=len(ACTIVE_CAMERAS))

    chart_column, activity_column = st.columns([1.25, 1])
    with chart_column:
        if frame.empty:
            st.info("Incident charts will appear when the database contains records.")
        else:
            st.plotly_chart(
                daily_trend_chart(frame), width="stretch", key="overview_trend"
            )
            st.plotly_chart(
                distribution_chart(frame), width="stretch", key="overview_distribution"
            )
    with activity_column:
        st.subheader("Recent security alerts")
        if frame.empty:
            st.info("No incidents have been recorded.")
        else:
            for record in frame.head(6).itertuples(index=False):
                timestamp = (
                    record.timestamp.strftime("%d %b %Y · %H:%M:%S")
                    if pd.notna(record.timestamp)
                    else "Time unavailable"
                )
                person_id = record.track_id if pd.notna(record.track_id) else "N/A"
                st.markdown(
                    f"**{record.incident_type}** · {record.camera_name}  \n"
                    f"{timestamp} · Person ID: {person_id} · Zone: "
                    f"{record.zone_name or 'Not specified'}"
                )
                st.divider()
        st.button(
            "Open incident management",
            key="overview_incidents",
            use_container_width=True,
            on_click=navigate_to,
            args=("Incident Management",),
        )

    st.subheader("Camera status overview")
    if not ACTIVE_CAMERAS:
        st.info("No cameras are configured in the backend.")
    else:
        camera_columns = st.columns(min(len(ACTIVE_CAMERAS), 3))
        for index, camera in enumerate(ACTIVE_CAMERAS):
            with camera_columns[index % len(camera_columns)]:
                st.markdown(f"**{camera.name}** · `{camera.camera_id}`")
                st.caption(_camera_status(camera))
    st.caption(f"Overview snapshot · {date.today().strftime('%d %B %Y')}")
