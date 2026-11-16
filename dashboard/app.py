import sqlite3
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT_PATH = Path(__file__).resolve().parents[1]
if str(ROOT_PATH) not in sys.path:
    sys.path.insert(0, str(ROOT_PATH))

from dashboard import database
from dashboard.style import apply_dashboard_style
from dashboard.views import analytics, cameras, incidents, overview, settings, zones


DATABASE_PATH = ROOT_PATH / "incidents.db"
PAGES = [
    "Overview",
    "Camera Monitoring",
    "Incident Management",
    "Analytics & Reports",
    "Camera & Zone Management",
    "System Logs & Settings",
]

st.set_page_config(
    page_title="Campus Security Operations",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)
apply_dashboard_style()


@st.cache_data(ttl=30)
def get_incidents(database_path: str) -> pd.DataFrame:
    return database.load_incidents(Path(database_path))


def navigate_to(page: str) -> None:
    st.session_state["navigation"] = page


with st.sidebar:
    st.markdown("## 🛡️ Campus Security")
    st.caption("UNIVERSITY OPERATIONS")
    st.radio("Workspace", PAGES, key="navigation", label_visibility="collapsed")
    st.divider()
    if st.button("↻ Refresh incident data", use_container_width=True):
        get_incidents.clear()
        st.rerun()
    st.caption("Incident records are accessed read-only.")
    st.caption(f"Updated {datetime.now().strftime('%H:%M:%S')}")

try:
    incident_data = get_incidents(str(DATABASE_PATH))
except FileNotFoundError as error:
    st.error(f"Incident database not found. {error}")
    st.info("Start the existing incident logger to create the database.")
    st.stop()
except sqlite3.Error as error:
    st.error(f"Could not read the incident database: {error}")
    st.stop()

incident_data["timestamp"] = pd.to_datetime(
    incident_data["timestamp"], errors="coerce"
)

page_title = st.session_state.get("navigation", PAGES[0])
header_left, header_right = st.columns([3, 1])
with header_left:
    st.markdown(
        f'<div class="eyebrow">CAMPUS SECURITY MONITORING</div>'
        f'<h1 class="page-title">{page_title}</h1>',
        unsafe_allow_html=True,
    )
with header_right:
    st.markdown(
        '<div class="system-status"><span class="status-dot"></span>'
        "DATABASE CONNECTED</div>",
        unsafe_allow_html=True,
    )
    st.caption(datetime.now().strftime("%A, %d %B %Y · %H:%M"))
st.divider()

if page_title == "Overview":
    overview.render(incident_data, navigate_to)
elif page_title == "Camera Monitoring":
    cameras.render(incident_data, DATABASE_PATH, get_incidents.clear)
elif page_title == "Incident Management":
    incidents.render(incident_data, DATABASE_PATH, get_incidents.clear)
elif page_title == "Analytics & Reports":
    analytics.render(incident_data)
elif page_title == "Camera & Zone Management":
    zones.render()
else:
    settings.render()
