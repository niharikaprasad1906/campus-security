"""
cameras.py — Camera configuration for Campus Security system.

Each Camera object groups a video source with its zones and tracker settings.
main.py iterates over ACTIVE_CAMERAS; adding a new camera only requires
defining it here.

For the current prototype only one camera (Main Gate) is active.
"""

from dataclasses import dataclass, field
from typing import List
from zones import MAIN_GATE_ZONES, Zone


@dataclass
class Camera:
    """Configuration for a single CCTV camera."""

    camera_id: str          # Unique machine-readable ID, e.g. 'cam_01'
    name: str               # Human-readable label, e.g. 'Main Gate'
    video_path: str         # Path to video file or RTSP stream URL
    zones: List[Zone]       # Zones monitored by this camera
    tracker_config: str = "custom_botsort.yaml"
    conf: float = 0.3
    imgsz: int = 640
    model_path: str = "yolo26n.pt"

    # Permitted movement hours: movement OUTSIDE this range triggers after-hours alert.
    # Format: (start_hour_24h, end_hour_24h)
    permitted_hours: tuple = (6, 22)   # 06:00 – 22:00


# ---------------------------------------------------------------------------
# Active cameras
# ---------------------------------------------------------------------------

MAIN_GATE_CAMERA = Camera(
    camera_id="cam_01",
    name="Main Gate",
    video_path="sample_videos/campus.avi",
    zones=MAIN_GATE_ZONES,
    tracker_config="custom_botsort.yaml",
    conf=0.3,
    imgsz=640,
    model_path="yolo26n.pt",
    permitted_hours=(6, 22),
)

# Add future cameras here, e.g.:
# PARKING_LOT_CAMERA = Camera(
#     camera_id="cam_02",
#     name="Parking Lot",
#     video_path="sample_videos/parking.avi",
#     zones=[...],
# )

ACTIVE_CAMERAS = [MAIN_GATE_CAMERA]
