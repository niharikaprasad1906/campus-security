import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from dashboard.components import SEVERITY_COLORS, with_derived_fields


CHART_LAYOUT = {
    "paper_bgcolor": "rgba(0,0,0,0)",
    "plot_bgcolor": "rgba(0,0,0,0)",
    "font": {"color": "#dce6f4"},
    "margin": {"l": 15, "r": 15, "t": 45, "b": 15},
    "legend": {"orientation": "h", "y": -0.22},
}


def distribution_chart(frame: pd.DataFrame) -> go.Figure:
    counts = frame["incident_type"].value_counts().rename_axis("Incident").reset_index(
        name="Count"
    )
    figure = px.pie(
        counts,
        names="Incident",
        values="Count",
        hole=0.62,
        color_discrete_sequence=["#ff6577", "#ffad5c", "#f3cb62", "#b69aff"],
    )
    figure.update_traces(textinfo="percent+label", hovertemplate="%{label}: %{value}<extra></extra>")
    figure.update_layout(**CHART_LAYOUT, title="Incidents by type")
    return figure


def daily_trend_chart(frame: pd.DataFrame) -> go.Figure:
    dates = pd.to_datetime(frame["timestamp"], errors="coerce").dropna().dt.date
    counts = dates.value_counts().sort_index()
    figure = px.line(
        x=counts.index,
        y=counts.values,
        markers=True,
        labels={"x": "Date", "y": "Incidents"},
        color_discrete_sequence=["#63a8ff"],
    )
    figure.update_traces(line={"width": 3}, hovertemplate="%{x}: %{y} incidents<extra></extra>")
    figure.update_layout(**CHART_LAYOUT, title="Daily incident trend")
    return figure


def camera_chart(frame: pd.DataFrame) -> go.Figure:
    counts = frame.groupby("camera_name", dropna=False).size().sort_values()
    figure = px.bar(
        x=counts.values,
        y=counts.index.fillna("Unknown camera"),
        orientation="h",
        labels={"x": "Incidents", "y": "Camera"},
        color_discrete_sequence=["#63a8ff"],
    )
    figure.update_layout(**CHART_LAYOUT, title="Incidents by camera")
    return figure


def hourly_chart(frame: pd.DataFrame) -> go.Figure:
    hours = pd.to_datetime(frame["timestamp"], errors="coerce").dropna().dt.hour
    counts = hours.value_counts().reindex(range(24), fill_value=0)
    figure = px.bar(
        x=[f"{hour:02d}:00" for hour in counts.index],
        y=counts.values,
        labels={"x": "Hour", "y": "Incidents"},
        color_discrete_sequence=["#b69aff"],
    )
    figure.update_layout(**CHART_LAYOUT, title="Incidents by hour")
    return figure


def weekly_chart(frame: pd.DataFrame) -> go.Figure:
    timestamps = pd.to_datetime(frame["timestamp"], errors="coerce").dropna()
    weeks = timestamps.dt.to_period("W-SUN").dt.start_time.dt.date
    counts = weeks.value_counts().sort_index()
    figure = px.bar(
        x=[week.strftime("%d %b %Y") for week in counts.index],
        y=counts.values,
        labels={"x": "Week commencing", "y": "Incidents"},
        color_discrete_sequence=["#41c994"],
    )
    figure.update_layout(**CHART_LAYOUT, title="Weekly incident totals")
    return figure


def severity_chart(frame: pd.DataFrame) -> go.Figure:
    enriched = with_derived_fields(frame)
    counts = enriched["severity"].value_counts().rename_axis("Severity").reset_index(
        name="Count"
    )
    figure = px.pie(
        counts,
        names="Severity",
        values="Count",
        hole=0.58,
        color="Severity",
        color_discrete_map=SEVERITY_COLORS,
    )
    figure.update_layout(**CHART_LAYOUT, title="Derived severity distribution")
    return figure
