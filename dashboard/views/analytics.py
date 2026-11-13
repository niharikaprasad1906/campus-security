import pandas as pd
import streamlit as st

from dashboard.charts import (
    camera_chart,
    daily_trend_chart,
    distribution_chart,
    hourly_chart,
    severity_chart,
    weekly_chart,
)
from dashboard.components import (
    camera_options,
    date_bounds,
    date_filter,
    incident_type_options,
)


def render(frame: pd.DataFrame) -> None:
    st.caption(
        "Charts and downloads are generated from the currently filtered database "
        "records. Severity is derived from incident type."
    )
    if frame.empty:
        st.info("Analytics will appear after incidents are recorded.")
        return

    minimum_date, maximum_date = date_bounds(frame)
    filter_columns = st.columns([1.4, 1, 1, 1])
    date_range = filter_columns[0].date_input(
        "Date range",
        value=(minimum_date, maximum_date),
        min_value=minimum_date,
        max_value=maximum_date,
        key="analytics_date_range",
    )
    selected_cameras = filter_columns[1].multiselect(
        "Camera", camera_options(frame), key="analytics_cameras"
    )
    selected_types = filter_columns[2].multiselect(
        "Incident type", incident_type_options(frame), key="analytics_types"
    )
    selected_review_status = filter_columns[3].multiselect(
        "Review status",
        ["Pending", "Reviewed"],
        key="analytics_review_status",
    )
    if len(date_range) != 2:
        st.warning("Select both a start and end date.")
        return

    filtered = date_filter(frame, date_range[0], date_range[1])
    if selected_cameras:
        filtered = filtered[filtered["camera_name"].isin(selected_cameras)]
    if selected_types:
        filtered = filtered[filtered["incident_type"].isin(selected_types)]
    if selected_review_status:
        filtered = filtered[
            filtered["review_status"].isin(selected_review_status)
        ]

    st.metric("Incidents in selected range", len(filtered))
    if filtered.empty:
        st.info("No incidents match the selected analytics filters.")
        return

    left, right = st.columns(2)
    with left:
        st.plotly_chart(daily_trend_chart(filtered), width="stretch")
        st.plotly_chart(camera_chart(filtered), width="stretch")
        st.plotly_chart(weekly_chart(filtered), width="stretch")
    with right:
        st.plotly_chart(distribution_chart(filtered), width="stretch")
        st.plotly_chart(hourly_chart(filtered), width="stretch")
        st.plotly_chart(severity_chart(filtered), width="stretch")

    st.subheader("Incident report")
    summary = (
        filtered.groupby("incident_type", dropna=False)
        .size()
        .rename("Incidents")
        .reset_index()
        .rename(columns={"incident_type": "Incident type"})
    )
    camera_summary = (
        filtered.groupby("camera_name", dropna=False)
        .size()
        .rename("Incidents")
        .reset_index()
        .rename(columns={"camera_name": "Camera"})
    )
    report_column, camera_column = st.columns(2)
    with report_column:
        st.dataframe(summary, hide_index=True, width="stretch")
    with camera_column:
        st.dataframe(camera_summary, hide_index=True, width="stretch")
    csv_report = filtered.to_csv(index=False).encode("utf-8")
    st.download_button(
        "Download filtered incident report (CSV)",
        data=csv_report,
        file_name="campus-security-report.csv",
        mime="text/csv",
    )
