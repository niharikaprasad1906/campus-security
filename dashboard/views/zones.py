import hmac
import os
from dataclasses import replace
from pathlib import Path

import pandas as pd
import streamlit as st

from cameras import ACTIVE_CAMERAS
from zones import save_zone_configuration


ROOT_PATH = Path(__file__).resolve().parents[2]


def _frame_dimensions(camera: object) -> tuple[int, int] | None:
    recording = (ROOT_PATH / camera.video_path).resolve()
    if not recording.is_file():
        return None

    import cv2

    capture = cv2.VideoCapture(str(recording))
    try:
        if not capture.isOpened():
            return None
        width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        return (width, height) if width > 0 and height > 0 else None
    finally:
        capture.release()


def _admin_access_enabled() -> bool:
    admin_password = os.environ.get("CAMPUS_SECURITY_ADMIN_PASSWORD")
    if not admin_password:
        st.warning(
            "Zone editing is read-only because no admin password is configured. "
            "Set CAMPUS_SECURITY_ADMIN_PASSWORD before starting Streamlit to enable it."
        )
        return False

    if st.session_state.get("zone_admin_authorized"):
        if st.button("Lock zone editing", key="lock_zone_editing"):
            st.session_state["zone_admin_authorized"] = False
            st.rerun()
        return True

    with st.form("zone_admin_login"):
        submitted_password = st.text_input("Admin password", type="password")
        submitted = st.form_submit_button("Unlock zone editing")
    if submitted:
        if hmac.compare_digest(submitted_password, admin_password):
            st.session_state["zone_admin_authorized"] = True
            st.rerun()
        else:
            st.error("The admin password is incorrect.")
    return False


def _zone_table(camera: object) -> pd.DataFrame:
    rows = []
    for zone in camera.zones:
        enabled_rules = [
            rule.replace("_", " ").title()
            for rule, enabled in zone.rules.items()
            if enabled
        ]
        rows.append(
            {
                "Zone": zone.name,
                "Type": (
                    "Restricted"
                    if zone.rules.get("restricted")
                    else "Crowd monitoring"
                    if zone.rules.get("crowd")
                    else "Monitoring"
                ),
                "Coordinates": f"({zone.x1}, {zone.y1}) – ({zone.x2}, {zone.y2})",
                "Rules": ", ".join(enabled_rules) or "None",
                "Crowd threshold": (
                    str(zone.crowd_threshold) if zone.rules.get("crowd") else "—"
                ),
                "Loiter threshold (s)": (
                    str(zone.loiter_threshold_s)
                    if zone.rules.get("loitering")
                    else "—"
                ),
            }
        )
    return pd.DataFrame(rows)


def render() -> None:
    st.caption(
        "Camera and zone configuration is loaded by the detection backend. "
        "Saving zone changes updates the shared configuration file; restart a "
        "separately running detection process to load them."
    )
    if not ACTIVE_CAMERAS:
        st.info("No cameras or zones are configured in the backend.")
        return

    camera_rows = [
        {
            "Camera ID": camera.camera_id,
            "Camera": camera.name,
            "Configured video source": camera.video_path,
            "Monitoring status": "In backend configuration",
            "Live connection": "Not verified",
        }
        for camera in ACTIVE_CAMERAS
    ]
    st.subheader("Configured cameras")
    st.dataframe(pd.DataFrame(camera_rows), hide_index=True, width="stretch")
    st.caption(
        "A camera being present in the backend configuration does not confirm "
        "that a live device is connected."
    )

    st.subheader("Monitoring zones")
    for camera in ACTIVE_CAMERAS:
        st.markdown(f"#### {camera.name} · `{camera.camera_id}`")
        if not camera.zones:
            st.info("No zones are configured for this camera.")
            continue
        st.dataframe(_zone_table(camera), hide_index=True, width="stretch")

    if not _admin_access_enabled():
        return

    st.success("Admin access enabled for this dashboard session.")
    for camera in ACTIVE_CAMERAS:
        if not camera.zones:
            continue
        st.subheader(f"Edit zones · {camera.name}")
        frame_dimensions = _frame_dimensions(camera)
        if frame_dimensions:
            frame_width, frame_height = frame_dimensions
            st.caption(f"Coordinates are validated against {frame_width} × {frame_height} source frames.")
        else:
            frame_width = frame_height = None
            st.warning("Source dimensions are unavailable; coordinates will be checked for valid rectangle bounds only.")

        zone_names = [zone.name for zone in camera.zones]
        selected_name = st.selectbox(
            "Zone to configure",
            zone_names,
            key=f"zone_to_edit_{camera.camera_id}",
        )
        selected_zone = next(zone for zone in camera.zones if zone.name == selected_name)
        max_x = frame_width - 1 if frame_width else 8191
        max_y = frame_height - 1 if frame_height else 8191
        with st.form(f"zone_editor_{camera.camera_id}_{selected_name}"):
            edited_name = st.text_input(
                "Zone name",
                value=selected_zone.name,
                max_chars=80,
            )
            x1_column, y1_column, x2_column, y2_column = st.columns(4)
            x1 = x1_column.number_input(
                "Left (x1)", min_value=0, max_value=max_x, value=selected_zone.x1
            )
            y1 = y1_column.number_input(
                "Top (y1)", min_value=0, max_value=max_y, value=selected_zone.y1
            )
            x2 = x2_column.number_input(
                "Right (x2)", min_value=1, max_value=max_x, value=selected_zone.x2
            )
            y2 = y2_column.number_input(
                "Bottom (y2)", min_value=1, max_value=max_y, value=selected_zone.y2
            )
            restricted = st.checkbox(
                "Restricted-zone intrusion",
                value=selected_zone.rules.get("restricted", False),
            )
            crowd = st.checkbox(
                "Crowd monitoring",
                value=selected_zone.rules.get("crowd", False),
            )
            loitering = st.checkbox(
                "Loitering monitoring",
                value=selected_zone.rules.get("loitering", False),
            )
            after_hours = st.checkbox(
                "After-hours monitoring",
                value=selected_zone.rules.get("after_hours", False),
            )
            crowd_threshold = st.number_input(
                "Crowd threshold (people)",
                min_value=1,
                max_value=1000,
                value=selected_zone.crowd_threshold,
                disabled=not crowd,
            )
            loiter_threshold = st.number_input(
                "Loitering threshold (seconds)",
                min_value=1.0,
                max_value=3600.0,
                value=float(selected_zone.loiter_threshold_s),
                step=1.0,
                disabled=not loitering,
            )
            submitted = st.form_submit_button("Save zone configuration", type="primary")

        if submitted:
            edited_zone = replace(
                selected_zone,
                name=edited_name.strip(),
                x1=int(x1),
                y1=int(y1),
                x2=int(x2),
                y2=int(y2),
                rules={
                    "restricted": restricted,
                    "crowd": crowd,
                    "loitering": loitering,
                    "after_hours": after_hours,
                },
                crowd_threshold=int(crowd_threshold),
                loiter_threshold_s=float(loiter_threshold),
            )
            updated_zones = [
                edited_zone if zone.name == selected_name else zone
                for zone in camera.zones
            ]
            try:
                save_zone_configuration(
                    camera.camera_id,
                    updated_zones,
                    frame_width=frame_width,
                    frame_height=frame_height,
                )
            except (OSError, ValueError) as error:
                st.error(f"Could not save zone configuration: {error}")
            else:
                camera.zones = updated_zones
                st.success(
                    "Zone configuration saved. A separately running detector "
                    "must be restarted to load the new settings."
                )
                st.rerun()
