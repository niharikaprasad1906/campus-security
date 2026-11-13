from pathlib import Path

import streamlit as st


ROOT_PATH = Path(__file__).resolve().parents[2]
INCIDENT_LOG_PATH = ROOT_PATH / "incident_log.txt"


def render() -> None:
    st.caption("Only settings and logs backed by existing project functionality are shown.")
    st.subheader("System status")
    st.success("Dashboard is connected to the existing incident database.")
    st.info(
        "The detection model and camera capture process are managed separately. "
        "Opening this dashboard does not start or stop them."
    )

    st.subheader("Available event log")
    if INCIDENT_LOG_PATH.is_file():
        try:
            with INCIDENT_LOG_PATH.open("r", encoding="utf-8", errors="replace") as log_file:
                lines = log_file.readlines()
        except OSError as error:
            st.error(f"Could not read the event log: {error}")
        else:
            st.caption(f"Showing the latest {min(len(lines), 100)} lines from incident_log.txt.")
            if lines:
                st.code("".join(lines[-100:]), language="text")
            else:
                st.info("The event log exists but contains no entries.")
    else:
        st.info("No incident_log.txt file is available.")
    st.caption(
        "Startup, camera-connection and detection-service logs are not exposed "
        "by the current backend."
    )

    st.subheader("Dashboard settings")
    st.markdown(
        "- **Refresh:** use *Refresh incident data* in the sidebar to reload records.\n"
        "- **Appearance:** dark security-operations theme.\n"
        "- **Storage:** incident database is opened read-only by the dashboard.\n"
        "- **Review workflow, notifications, and data retention:** not implemented "
        "in the current backend."
    )
