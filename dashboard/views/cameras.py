import hashlib
import sqlite3
import tempfile
from pathlib import Path
from typing import Callable

import pandas as pd
import streamlit as st

from cameras import ACTIVE_CAMERAS
from dashboard.playback import process_sample_video


ROOT_PATH = Path(__file__).resolve().parents[2]


def _recent_camera_incidents(frame: pd.DataFrame, camera_id: str) -> pd.DataFrame:
    return frame.loc[frame["camera_id"].eq(camera_id)].sort_values(
        "timestamp", ascending=False
    )


def render(
    frame: pd.DataFrame,
    database_path: Path,
    refresh_incidents: Callable[[], None],
) -> None:
    st.caption(
        "Configured recordings are available for demonstration. No live CCTV "
        "connection is configured or claimed by this dashboard."
    )
    if not ACTIVE_CAMERAS:
        st.info("No cameras are configured in the backend camera registry.")
        return

    camera_by_name = {camera.name: camera for camera in ACTIVE_CAMERAS}
    selected_name = st.selectbox("Select camera", list(camera_by_name))
    camera = camera_by_name[selected_name]
    configured_recording = (ROOT_PATH / camera.video_path).resolve()
    recordings = (
        {configured_recording.name: configured_recording}
        if configured_recording.is_file()
        else {}
    )
    recent = _recent_camera_incidents(frame, camera.camera_id)

    with st.container(border=True):
        title_column, status_column = st.columns([2, 1])
        title_column.subheader(camera.name)
        title_column.caption(f"Camera ID: {camera.camera_id}")
        if recordings:
            status_column.success("Recorded sample available")
        else:
            status_column.warning("No connected feed or recording available")
        st.info("Live stream: not connected. Recorded sample playback is independent of the YOLO backend.")
        if recordings:
            selected_recording = st.selectbox(
                "Select available sample recording",
                list(recordings),
                key="sample_recording",
            )
            with st.expander("Recorded sample playback", expanded=True):
                recording = recordings[selected_recording]
                playback_speed = st.select_slider(
                    "Completed video speed",
                    options=[1.0, 1.5, 2.0, 3.0],
                    value=2.0,
                    format_func=lambda speed: f"{speed:g}x",
                    key=f"playback_speed_{camera.camera_id}",
                )
                st.caption(
                    f"Recorded sample · {recording.relative_to(ROOT_PATH)} · "
                    "all frames are analyzed; the finished video plays faster"
                )
                run_key = f"fresh_playback_{camera.camera_id}"
                if st.button(
                    "Run fresh tracking and playback",
                    key=f"start_{run_key}",
                    type="primary",
                ):
                    st.session_state.pop(run_key, None)
                    st.markdown("#### Live tracking playback")
                    live_video = st.empty()
                    progress = st.progress(0, text="Loading detection model...")
                    id_status = st.empty()

                    def show_tracking_frame(
                        image: object,
                        current: int,
                        total: int,
                        tracker_ids: list[int],
                        canonical_ids: list[int],
                    ) -> None:
                        live_video.image(
                            image,
                            channels="BGR",
                            width="stretch",
                            caption=f"Tracking playback · frame {current:,} of {total:,}",
                        )
                        if current % 5 == 0 or current == total:
                            progress.progress(
                                min(current / max(total, 1), 1.0),
                                text=f"Analyzing frame {current:,} of {total:,}",
                            )
                            id_status.caption(
                                f"YOLO tracker IDs: {tracker_ids or 'none yet'} · "
                                f"Stable canonical IDs: {canonical_ids or 'none yet'}"
                            )

                    try:
                        result = process_sample_video(
                            camera=camera,
                            recording=recording,
                            database_path=database_path,
                            frame_callback=show_tracking_frame,
                            playback_speed=playback_speed,
                        )
                    except ModuleNotFoundError as error:
                        if error.name == "imageio_ffmpeg":
                            st.error(
                                "Playback dependency 'imageio-ffmpeg' is unavailable "
                                "in the Python environment running Streamlit."
                            )
                            st.code(
                                "python -m pip install -r dashboard/requirements.txt",
                                language="powershell",
                            )
                        elif error.name in {"ultralytics", "cv2"}:
                            st.error(
                                f"Backend dependency '{error.name}' is unavailable. "
                                "Run the dashboard with the project's backend environment."
                            )
                            st.code(
                                ".\\venv\\Scripts\\python.exe -m streamlit run dashboard/app.py",
                                language="powershell",
                            )
                        else:
                            raise
                    except (OSError, RuntimeError, sqlite3.Error, ValueError) as error:
                        st.error(f"Could not process this sample recording: {error}")
                    else:
                        st.session_state[run_key] = {
                            "recording": str(recording),
                            "video": result.video,
                            "canonical_ids": result.canonical_ids,
                            "tracker_ids": result.tracker_ids,
                            "incidents": result.incidents,
                            "frame_count": result.frame_count,
                            "fps": result.fps,
                            "playback_speed": result.playback_speed,
                        }
                        refresh_incidents()

                playback = st.session_state.get(run_key)
                if playback and playback["recording"] == str(recording):
                    if "incidents" not in playback:
                        legacy_incident_ids = playback.get("incident_ids", [])
                        camera_incidents = frame.loc[
                            frame["camera_id"].eq(camera.camera_id)
                        ]
                        playback["incidents"] = camera_incidents.loc[
                            camera_incidents["id"].isin(legacy_incident_ids)
                        ].copy()
                        st.session_state[run_key] = playback

                    st.subheader("Replay completed tracking video")
                    st.video(playback["video"], format="video/mp4")
                    st.caption(
                        f"Fresh run complete · {playback['frame_count']:,} frames · "
                        f"source {playback['fps']:g} FPS · "
                        f"replay {playback.get('playback_speed', 1.0):g}x"
                    )
                    id_column, canonical_column = st.columns(2)
                    id_column.subheader(
                        f"YOLO tracker IDs ({len(playback['tracker_ids'])})"
                    )
                    canonical_column.subheader(
                        f"Stable canonical IDs ({len(playback['canonical_ids'])})"
                    )
                    if playback["tracker_ids"]:
                        id_column.code(", ".join(map(str, playback["tracker_ids"])))
                    else:
                        id_column.info("No YOLO person track IDs were detected.")
                    if playback["canonical_ids"]:
                        canonical_column.code(
                            ", ".join(map(str, playback["canonical_ids"]))
                        )
                    else:
                        canonical_column.info("No canonical person IDs were detected.")

                    playback_incidents = playback.get("incidents")
                    if playback_incidents is None:
                        playback_incidents = frame.iloc[0:0].copy()
                    st.subheader(
                        f"New incident records from this run ({len(playback_incidents)})"
                    )
                    if playback_incidents.empty:
                        st.info(
                            "No new incident records were created in this run. "
                            "The detection backend may have found no new alerts, "
                            "or its duplicate-event protection may have skipped them."
                        )
                    else:
                        st.dataframe(
                            playback_incidents.rename(
                                columns={
                                    "id": "Record ID",
                                    "timestamp": "Timestamp",
                                    "incident_type": "Incident",
                                    "camera_id": "Camera ID",
                                    "camera_name": "Camera",
                                    "zone_name": "Zone",
                                    "track_id": "Person ID",
                                    "extra_info": "Details",
                                }
                            ),
                            hide_index=True,
                            width="stretch",
                        )
        else:
            st.markdown(
                '<div class="security-card"><div class="security-card-title">'
                "Video feed unavailable</div><div class='security-card-meta'>"
                "Connect a real camera source or add a clearly identified sample "
                "recording to enable playback.</div></div>",
                unsafe_allow_html=True,
            )

        with st.expander("Analyze your own video"):
            st.caption(
                "Upload a video to run person tracking and incident detection "
                f"using {camera.name}'s configured zones and rules. The uploaded "
                "file is temporary and is not saved by the dashboard."
            )
            uploaded_video = st.file_uploader(
                "Choose a video",
                type=[
                    "mp4", "avi", "mov", "mkv", "mpeg", "mpg",
                    "m4v", "webm", "wmv", "3gp",
                ],
                key=f"uploaded_video_{camera.camera_id}",
            )
            uploaded_bytes = uploaded_video.getvalue() if uploaded_video else None
            upload_hash = (
                hashlib.sha256(uploaded_bytes).hexdigest()
                if uploaded_bytes is not None
                else None
            )
            upload_run_key = f"uploaded_playback_{camera.camera_id}"
            playback_speed = st.select_slider(
                "Completed video speed",
                options=[1.0, 1.5, 2.0, 3.0],
                value=2.0,
                format_func=lambda speed: f"{speed:g}x",
                key=f"uploaded_playback_speed_{camera.camera_id}",
            )

            if st.button(
                "Analyze uploaded video",
                key=f"analyze_upload_{camera.camera_id}",
                type="primary",
                disabled=uploaded_bytes is None,
            ):
                st.session_state.pop(upload_run_key, None)
                st.markdown("#### Uploaded video analysis")
                live_video = st.empty()
                progress = st.progress(0, text="Loading detection model...")

                def show_uploaded_frame(
                    image: object,
                    current: int,
                    total: int,
                    tracker_ids: list[int],
                    canonical_ids: list[int],
                ) -> None:
                    live_video.image(
                        image,
                        channels="BGR",
                        width="stretch",
                        caption=f"Analyzing upload · frame {current:,} of {total:,}",
                    )
                    if current % 5 == 0 or current == total:
                        progress.progress(
                            min(current / max(total, 1), 1.0),
                            text=f"Analyzing frame {current:,} of {total:,}",
                        )

                try:
                    with tempfile.TemporaryDirectory(
                        prefix="campus-security-upload-"
                    ) as directory:
                        temporary_directory = Path(directory)
                        upload_path = temporary_directory / (
                            "upload" + Path(uploaded_video.name).suffix.lower()
                        )
                        upload_path.write_bytes(uploaded_bytes)
                        result = process_sample_video(
                            camera=camera,
                            recording=upload_path,
                            database_path=database_path,
                            frame_callback=show_uploaded_frame,
                            text_log_path=temporary_directory / "incidents.txt",
                            playback_speed=playback_speed,
                        )
                except ModuleNotFoundError as error:
                    if error.name == "imageio_ffmpeg":
                        st.error(
                            "Playback dependency 'imageio-ffmpeg' is unavailable "
                            "in the Python environment running Streamlit."
                        )
                    elif error.name in {"ultralytics", "cv2"}:
                        st.error(
                            f"Backend dependency '{error.name}' is unavailable. "
                            "Run the dashboard with the project's backend environment."
                        )
                        st.code(
                            ".\\venv\\Scripts\\python.exe -m streamlit run dashboard/app.py",
                            language="powershell",
                        )
                    else:
                        raise
                except (OSError, RuntimeError, sqlite3.Error, ValueError) as error:
                    st.error(f"Could not analyze the uploaded video: {error}")
                else:
                    st.session_state[upload_run_key] = {
                        "source_hash": upload_hash,
                        "source_name": uploaded_video.name,
                        "video": result.video,
                        "incidents": result.incidents,
                        "frame_count": result.frame_count,
                        "fps": result.fps,
                        "playback_speed": result.playback_speed,
                    }
                    refresh_incidents()

            uploaded_playback = st.session_state.get(upload_run_key)
            if uploaded_playback and uploaded_playback["source_hash"] == upload_hash:
                st.subheader("Replay analyzed video")
                st.video(uploaded_playback["video"], format="video/mp4")
                st.caption(
                    f"{uploaded_playback['source_name']} · "
                    f"{uploaded_playback['frame_count']:,} frames · "
                    f"source {uploaded_playback['fps']:g} FPS · "
                    f"replay {uploaded_playback['playback_speed']:g}x"
                )
                upload_incidents = uploaded_playback["incidents"]
                st.subheader(
                    f"New incident records from this upload ({len(upload_incidents)})"
                )
                if upload_incidents.empty:
                    st.info("No new incident records were created for this upload.")
                else:
                    st.dataframe(
                        upload_incidents.rename(
                            columns={
                                "id": "Record ID",
                                "timestamp": "Timestamp",
                                "incident_type": "Incident",
                                "camera_id": "Camera ID",
                                "camera_name": "Camera",
                                "zone_name": "Zone",
                                "track_id": "Person ID",
                                "extra_info": "Details",
                            }
                        ),
                        hide_index=True,
                        width="stretch",
                    )

        last_incident = recent.iloc[0] if not recent.empty else None
        if last_incident is None:
            st.caption("No incidents are recorded for this camera.")
        else:
            timestamp = last_incident["timestamp"]
            st.warning(
                f"Latest recorded alert: {last_incident['incident_type']} · "
                f"{timestamp if pd.notna(timestamp) else 'time unavailable'}"
            )
        st.caption(
            "Each fresh tracking run starts a new tracker session. "
            "Playback-generated incidents are saved in the existing incident database."
        )
