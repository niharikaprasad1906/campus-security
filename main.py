"""
main.py — Campus Security and Anomaly Detection System

Features
--------
- Full-frame person detection with YOLO.
- Configurable, independent monitoring zones (see zones.py).
- Restricted-zone intrusion detection (3-second grace period).
- Crowd detection per zone.
- Position-based loitering detection (tolerates ID switches — see loitering.py).
- After-hours movement detection.
- Structured SQLite incident logging with deduplication (see db.py).
- Multi-camera configuration (see cameras.py); currently single camera.

Controls
--------
  Q  — quit
"""

import cv2
import time
import datetime
from ultralytics import YOLO

from db import init_db, log_incident
from zones import Zone
from cameras import ACTIVE_CAMERAS
from loitering import LoiteringTracker
from reidentifier import ReIdentifier

# ---------------------------------------------------------------------------
# Developer / testing flags
# ---------------------------------------------------------------------------
after_hours_test = False   # Set True to trigger after-hours alerts regardless of time.

# ---------------------------------------------------------------------------
# Initialise database (safe to call on every startup)
# ---------------------------------------------------------------------------
init_db()


# ===========================================================================
# Per-camera processing state
# ===========================================================================

class CameraState:
    """
    Holds all mutable state for one camera so multiple cameras can run
    independently in the future.
    """

    def __init__(self, camera):
        self.camera = camera
        self.model = YOLO(camera.model_path)

        # One LoiteringTracker per zone that has loitering enabled.
        self.loitering_trackers = {
            zone.name: LoiteringTracker(zone.loiter_threshold_s)
            for zone in camera.zones
            if zone.rules.get("loitering")
        }

        # Intrusion state — per zone that has restricted rule enabled.
        # {zone_name: {'logged': bool, 'last_time': float}}
        self.intrusion_state = {
            zone.name: {"logged": False, "last_time": 0.0}
            for zone in camera.zones
            if zone.rules.get("restricted")
        }

        # Crowd state — per crowd zone.
        # {zone_name: bool}
        self.crowd_logged = {
            zone.name: False
            for zone in camera.zones
            if zone.rules.get("crowd")
        }

        # After-hours: track which slots have already triggered an alert
        # to avoid flooding. Keyed by zone_name, stores set of slot object ids.
        self.after_hours_logged_slots = {
            zone.name: set()
            for zone in camera.zones
            if zone.rules.get("after_hours")
        }

        # Global after-hours flag for display.
        self.after_hours_alert = False

        # Re-identification layer: maps unstable raw tracker IDs → stable
        # canonical IDs using colour histograms + spatial proximity.
        self.reidentifier = ReIdentifier()


def process_frame(state: CameraState, frame):
    """
    Run detection + tracking on a single frame and update all zone states.

    Returns
    -------
    output : numpy.ndarray
        Annotated frame ready for display.
    """
    cam = state.camera

    results = state.model.track(
        frame,
        persist=True,
        tracker=cam.tracker_config,
        conf=cam.conf,
        imgsz=cam.imgsz,
        verbose=False,
    )

    if not results or len(results) == 0:
        return frame.copy()

    output = results[0].plot()

    # Draw all zones.
    for zone in cam.zones:
        zone.draw(output)

    # -----------------------------------------------------------------------
    # Collect all person detections and sort them into zones.
    # -----------------------------------------------------------------------

    # zone_name -> list of (foot_x, foot_y, track_id | None)
    zone_detections: dict[str, list] = {z.name: [] for z in cam.zones}

    # zone_name -> count of people in zone (for crowd)
    zone_person_count: dict[str, int] = {z.name: 0 for z in cam.zones}

    # Global intrusion tracking per restricted zone for this frame.
    # {zone_name: (active: bool, latest_track_id: int | None)}
    intrusion_this_frame: dict[str, tuple] = {}

    current_hour = datetime.datetime.now().hour
    is_after_hours = after_hours_test or (
        current_hour >= cam.permitted_hours[1] or current_hour < cam.permitted_hours[0]
    )

    # active_raw_ids: collect every raw tracker ID seen this frame so we can
    # tell the ReIdentifier which IDs have disappeared.
    active_raw_ids: set = set()

    for box in results[0].boxes:
        if box.cls is None or len(box.cls) == 0:
            continue
        class_id = int(box.cls[0])
        if state.model.names.get(class_id) != "person":
            continue
        if box.xyxy is None or len(box.xyxy) == 0:
            continue

        x1, y1, x2, y2 = map(int, box.xyxy[0])
        foot_x = (x1 + x2) // 2
        foot_y = y2
        raw_id = int(box.id[0]) if (box.id is not None and len(box.id) > 0) else None

        # ── Re-identification ────────────────────────────────────────────
        # Map the raw tracker ID to a stable canonical ID (CID).
        # The CID persists across short occlusions even when the raw ID
        # changes, using colour histograms + spatial proximity matching.
        if raw_id is not None:
            active_raw_ids.add(raw_id)
            canonical_id = state.reidentifier.get_canonical_id(
                raw_id=raw_id,
                foot_x=foot_x,
                foot_y=foot_y,
                frame=frame,      # original frame for histogram extraction
                x1=x1, y1=y1, x2=x2, y2=y2,
            )
        else:
            canonical_id = None

        # Use canonical_id everywhere from here on.
        track_id = canonical_id

        # Draw foot-point dot.
        cv2.circle(output, (foot_x, foot_y), 6, (0, 0, 255), -1)

        # Draw stable canonical ID label above the foot-point.
        if canonical_id is not None:
            cv2.putText(
                output,
                f"CID:{canonical_id}",
                (foot_x - 20, foot_y - 22),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.45,
                (0, 255, 120),   # bright green — distinct from YOLO's own labels
                1,
            )

        # Check every zone.
        for zone in cam.zones:
            if zone.contains_point(foot_x, foot_y):
                zone_detections[zone.name].append((foot_x, foot_y, track_id))
                zone_person_count[zone.name] += 1

                if zone.rules.get("restricted"):
                    prev_active, prev_id = intrusion_this_frame.get(zone.name, (False, None))
                    intrusion_this_frame[zone.name] = (True, track_id or prev_id)

    # -----------------------------------------------------------------------
    # Update loitering trackers and handle loitering alerts.
    # -----------------------------------------------------------------------
    state.after_hours_alert = False

    for zone in cam.zones:
        # --- Loitering ---
        if zone.rules.get("loitering") and zone.name in state.loitering_trackers:
            tracker = state.loitering_trackers[zone.name]
            tracker.update_detections(zone_detections[zone.name])
            tracker.purge_expired()

            for slot in tracker.get_unlogged_loitering_slots():
                rep_id = slot.representative_id()
                log_incident(
                    "Loitering Detected",
                    camera_id=cam.camera_id,
                    camera_name=cam.name,
                    zone_name=zone.name,
                    track_id=rep_id,
                    extra_info=f"Duration: {int(slot.elapsed_seconds)}s; "
                               f"IDs observed: {sorted(slot.track_ids_seen)}",
                )
                tracker.mark_loitering_logged(slot)

            # Draw loitering timer for each active slot.
            for slot in tracker.slots:
                cv2.putText(
                    output,
                    f"{int(slot.elapsed_seconds)}s",
                    (slot.foot_x + 8, slot.foot_y - 10),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.55,
                    (255, 255, 0),
                    2,
                )

        # --- After-hours ---
        if zone.rules.get("after_hours") and is_after_hours:
            state.after_hours_alert = True
            for foot_x, foot_y, track_id in zone_detections[zone.name]:
                if track_id is not None:
                    logged_set = state.after_hours_logged_slots.setdefault(zone.name, set())
                    if track_id not in logged_set:
                        log_incident(
                            "After-Hours Movement",
                            camera_id=cam.camera_id,
                            camera_name=cam.name,
                            zone_name=zone.name,
                            track_id=track_id,
                        )
                        logged_set.add(track_id)

    # -----------------------------------------------------------------------
    # Intrusion detection — preserve the 3-second grace-period logic.
    # -----------------------------------------------------------------------
    intrusion_active_any = False
    for zone in cam.zones:
        if not zone.rules.get("restricted"):
            continue

        active, latest_id = intrusion_this_frame.get(zone.name, (False, None))
        z_state = state.intrusion_state[zone.name]

        if active:
            intrusion_active_any = True
            if not z_state["logged"]:
                log_incident(
                    "Restricted Zone Intrusion",
                    camera_id=cam.camera_id,
                    camera_name=cam.name,
                    zone_name=zone.name,
                    track_id=latest_id,
                )
                z_state["logged"] = True
            z_state["last_time"] = time.time()
        elif z_state["logged"] and (time.time() - z_state["last_time"]) > 3:
            z_state["logged"] = False

    # -----------------------------------------------------------------------
    # Crowd detection.
    # -----------------------------------------------------------------------
    crowd_alert_any = False
    crowd_status_texts = []

    for zone in cam.zones:
        if not zone.rules.get("crowd"):
            continue

        count = zone_person_count[zone.name]
        if count > zone.crowd_threshold:
            crowd_alert_any = True
            crowd_status_texts.append(f"{zone.name}: OVERCROWDED ({count})")
            if not state.crowd_logged.get(zone.name, False):
                log_incident(
                    "Overcrowding Detected",
                    camera_id=cam.camera_id,
                    camera_name=cam.name,
                    zone_name=zone.name,
                    extra_info=f"Person count: {count}",
                )
                state.crowd_logged[zone.name] = True
        else:
            crowd_status_texts.append(f"{zone.name}: OK ({count})")
            state.crowd_logged[zone.name] = False

    # -----------------------------------------------------------------------
    # HUD overlays.
    # -----------------------------------------------------------------------
    y_offset = 30

    # Zone / intrusion status.
    if intrusion_active_any:
        cv2.putText(output, "WARNING: RESTRICTED ZONE ENTRY!",
                    (20, y_offset), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
    else:
        cv2.putText(output, "Restricted Zone: CLEAR",
                    (20, y_offset), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 200, 0), 2)
    y_offset += 35

    # Crowd status.
    for txt in crowd_status_texts:
        color = (0, 0, 255) if "OVERCROWDED" in txt else (255, 255, 0)
        cv2.putText(output, txt, (20, y_offset), cv2.FONT_HERSHEY_SIMPLEX, 0.65, color, 2)
        y_offset += 30

    # Loitering warning.
    any_loitering = any(
        len(t.get_loitering_slots()) > 0
        for t in state.loitering_trackers.values()
    )
    if any_loitering:
        cv2.putText(output, "WARNING: LOITERING DETECTED!",
                    (20, y_offset), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
        y_offset += 35

    # After-hours warning.
    if state.after_hours_alert:
        cv2.putText(output, "WARNING: AFTER-HOURS MOVEMENT!",
                    (20, y_offset), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

    # Camera label (top-right).
    label = f"CAM: {cam.name}"
    (lw, lh), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
    h, w = output.shape[:2]
    cv2.putText(output, label, (w - lw - 10, 25),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 2)

    # Gallery size (diagnostic) — bottom-left corner.
    gallery_txt = f"ReID gallery: {state.reidentifier.gallery_size}"
    h_frame, w_frame = output.shape[:2]
    cv2.putText(output, gallery_txt,
                (10, h_frame - 10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.42, (140, 140, 140), 1)

    # ── Tell the ReIdentifier which raw IDs disappeared this frame ──────
    state.reidentifier.end_frame(active_raw_ids)

    return output


# ===========================================================================
# Main loop
# ===========================================================================

def run():
    """Open each active camera and process frames until the user quits."""

    camera_states = []
    caps = []

    for cam in ACTIVE_CAMERAS:
        cap = cv2.VideoCapture(cam.video_path)
        if not cap.isOpened():
            print(f"[ERROR] Could not open video for camera '{cam.name}': {cam.video_path}")
            continue
        print(f"[INFO] Camera '{cam.name}' — "
              f"{int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))}x"
              f"{int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))} @ "
              f"{cap.get(cv2.CAP_PROP_FPS):.1f} FPS")
        caps.append(cap)
        camera_states.append(CameraState(cam))

    if not caps:
        print("[ERROR] No cameras could be opened. Exiting.")
        return

    window_name = "Campus Security — Zone Detection"
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)

    while True:
        all_done = True
        frames_to_show = []

        for cap, state in zip(caps, camera_states):
            success, frame = cap.read()
            if not success:
                continue
            all_done = False
            annotated = process_frame(state, frame)
            frames_to_show.append(annotated)

        if all_done:
            print("[INFO] All video streams ended.")
            break

        # If multiple cameras: tile them side by side (future use).
        if len(frames_to_show) == 1:
            display = frames_to_show[0]
        else:
            import numpy as np
            # Resize all to the same height before concatenating.
            target_h = frames_to_show[0].shape[0]
            resized = []
            for f in frames_to_show:
                if f.shape[0] != target_h:
                    scale = target_h / f.shape[0]
                    f = cv2.resize(f, (int(f.shape[1] * scale), target_h))
                resized.append(f)
            display = np.hstack(resized)

        cv2.imshow(window_name, display)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            print("[INFO] User quit.")
            break

    for cap in caps:
        cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    run()
