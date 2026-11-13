"""
zones.py — Configurable monitoring zone definitions.

Each Zone is an independent rectangle with its own rules.
Add new zones here without touching main.py logic.

Zone rules (all default to False):
    restricted   — flag any person who enters as a zone intrusion
    crowd        — flag when person count exceeds crowd_threshold
    loitering    — flag persons who stay longer than loiter_threshold_s
    after_hours  — flag any movement detected outside permitted hours
"""

import json
import math
import os
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, Tuple


ZONE_CONFIG_PATH = Path(__file__).with_name("dashboard") / "zone_config.json"
ZONE_RULES = {"restricted", "crowd", "loitering", "after_hours"}


@dataclass
class Zone:
    """Represents a single rectangular monitoring zone."""

    name: str
    x1: int
    y1: int
    x2: int
    y2: int
    color_bgr: Tuple[int, int, int] = (0, 0, 255)  # Default red

    # Which incident types this zone participates in
    rules: Dict[str, bool] = field(default_factory=lambda: {
        "restricted": False,
        "crowd": False,
        "loitering": False,
        "after_hours": False,
    })

    # Per-zone thresholds (override global defaults if needed)
    crowd_threshold: int = 5
    loiter_threshold_s: float = 15.0

    def contains_point(self, x: int, y: int) -> bool:
        """Return True if (x, y) is inside this zone."""
        return self.x1 <= x <= self.x2 and self.y1 <= y <= self.y2

    def draw(self, frame):
        """Draw the zone rectangle and label onto a frame (in-place)."""
        import cv2
        cv2.rectangle(frame, (self.x1, self.y1), (self.x2, self.y2), self.color_bgr, 2)
        cv2.putText(
            frame,
            self.name,
            (self.x1 + 4, self.y1 + 18),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            self.color_bgr,
            1,
        )


def _validated_zone(
    zone: Zone,
    frame_width: int | None = None,
    frame_height: int | None = None,
) -> Zone:
    if not isinstance(zone.name, str) or not zone.name.strip() or len(zone.name) > 80:
        raise ValueError("Zone names must contain 1 to 80 characters.")
    if any(
        isinstance(value, bool) or not isinstance(value, int)
        for value in (zone.x1, zone.y1, zone.x2, zone.y2)
    ):
        raise ValueError("Zone coordinates must be whole numbers.")
    if zone.x1 < 0 or zone.y1 < 0 or zone.x1 >= zone.x2 or zone.y1 >= zone.y2:
        raise ValueError("Zone coordinates must be non-negative and form a non-empty rectangle.")
    if frame_width is not None and zone.x2 >= frame_width:
        raise ValueError(f"Zone x2 must be smaller than frame width ({frame_width}).")
    if frame_height is not None and zone.y2 >= frame_height:
        raise ValueError(f"Zone y2 must be smaller than frame height ({frame_height}).")
    if (
        isinstance(zone.crowd_threshold, bool)
        or not isinstance(zone.crowd_threshold, int)
        or not 1 <= zone.crowd_threshold <= 1000
    ):
        raise ValueError("Crowd threshold must be between 1 and 1000 people.")
    if (
        isinstance(zone.loiter_threshold_s, bool)
        or not isinstance(zone.loiter_threshold_s, (int, float))
        or not math.isfinite(zone.loiter_threshold_s)
        or not 1 <= zone.loiter_threshold_s <= 3600
    ):
        raise ValueError("Loiter threshold must be between 1 and 3600 seconds.")
    if not set(zone.rules).issubset(ZONE_RULES):
        raise ValueError("Zone contains an unsupported monitoring rule.")
    if any(not isinstance(value, bool) for value in zone.rules.values()):
        raise ValueError("Zone monitoring rules must be enabled or disabled.")
    if len(zone.color_bgr) != 3 or any(
        isinstance(channel, bool) or not isinstance(channel, int) or not 0 <= channel <= 255
        for channel in zone.color_bgr
    ):
        raise ValueError("Zone color must contain three values between 0 and 255.")
    return zone


def _zone_from_json(data: dict) -> Zone:
    if not isinstance(data, dict):
        raise ValueError("Zone configuration entries must be objects.")
    color = data.get("color_bgr", (0, 0, 255))
    rules = data.get("rules", {})
    if not isinstance(color, (list, tuple)) or not isinstance(rules, dict):
        raise ValueError("Zone colors and rules have invalid formats.")
    zone = Zone(
        name=data.get("name", ""),
        x1=data.get("x1"),
        y1=data.get("y1"),
        x2=data.get("x2"),
        y2=data.get("y2"),
        color_bgr=tuple(color),
        rules=rules,
        crowd_threshold=data.get("crowd_threshold", 5),
        loiter_threshold_s=data.get("loiter_threshold_s", 15.0),
    )
    return _validated_zone(zone)


def load_zone_configuration(
    camera_id: str,
    defaults: list[Zone],
    config_path: Path = ZONE_CONFIG_PATH,
) -> list[Zone]:
    def copy_defaults() -> list[Zone]:
        return [
            _validated_zone(
                Zone(
                    name=zone.name,
                    x1=zone.x1,
                    y1=zone.y1,
                    x2=zone.x2,
                    y2=zone.y2,
                    color_bgr=tuple(zone.color_bgr),
                    rules=dict(zone.rules),
                    crowd_threshold=zone.crowd_threshold,
                    loiter_threshold_s=zone.loiter_threshold_s,
                )
            )
            for zone in defaults
        ]

    if not config_path.exists():
        return copy_defaults()
    try:
        configuration = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"Could not read saved zone configuration: {error}") from error
    if not isinstance(configuration, dict):
        raise ValueError("Saved zone configuration must be a JSON object.")
    camera_zones = configuration.get(camera_id)
    if camera_zones is None:
        return copy_defaults()
    if not isinstance(camera_zones, list) or not camera_zones:
        raise ValueError(f"Saved zone list for {camera_id} must not be empty.")
    zones = [_zone_from_json(item) for item in camera_zones]
    if len({zone.name.strip().casefold() for zone in zones}) != len(zones):
        raise ValueError(f"Zone names for {camera_id} must be unique.")
    return zones


def save_zone_configuration(
    camera_id: str,
    zones: list[Zone],
    frame_width: int | None = None,
    frame_height: int | None = None,
    config_path: Path = ZONE_CONFIG_PATH,
) -> None:
    if not camera_id or not zones:
        raise ValueError("A camera ID and at least one monitoring zone are required.")
    if len(zones) > 32:
        raise ValueError("At most 32 monitoring zones can be saved per camera.")
    validated = [
        _validated_zone(zone, frame_width, frame_height) for zone in zones
    ]
    if len({zone.name.strip().casefold() for zone in validated}) != len(validated):
        raise ValueError("Zone names must be unique.")
    config_path.parent.mkdir(parents=True, exist_ok=True)
    if config_path.exists():
        try:
            configuration = json.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError(f"Could not read saved zone configuration: {error}") from error
        if not isinstance(configuration, dict):
            raise ValueError("Saved zone configuration must be a JSON object.")
    else:
        configuration = {}

    configuration[camera_id] = [asdict(zone) for zone in validated]
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=config_path.parent,
            prefix=f".{config_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            json.dump(configuration, temporary_file, indent=2)
            temporary_file.write("\n")
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        os.replace(temporary_path, config_path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


# ---------------------------------------------------------------------------
# Zone definitions for the campus prototype
# ---------------------------------------------------------------------------

# Restricted zone — same coordinates as the original implementation.
# Triggers: intrusion, loitering, after-hours.
RESTRICTED_ZONE = Zone(
    name="Restricted Zone",
    x1=300,
    y1=150,
    x2=600,
    y2=400,
    color_bgr=(0, 0, 255),       # Red
    rules={
        "restricted": True,
        "crowd": False,
        "loitering": True,
        "after_hours": True,
    },
    loiter_threshold_s=15.0,
)

# Crowd-monitoring zone — larger area covering the main passage.
# Triggers: overcrowding only.
CROWD_ZONE = Zone(
    name="Crowd Zone",
    x1=150,
    y1=80,
    x2=650,
    y2=500,
    color_bgr=(0, 165, 255),     # Orange
    rules={
        "restricted": False,
        "crowd": True,
        "loitering": False,
        "after_hours": False,
    },
    crowd_threshold=5,
)

# All active zones for the Main Gate camera.
# To add a new zone, define it above and append it here.
MAIN_GATE_ZONES = load_zone_configuration(
    "cam_01", [RESTRICTED_ZONE, CROWD_ZONE]
)
