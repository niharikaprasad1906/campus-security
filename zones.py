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

from dataclasses import dataclass, field
from typing import Tuple, Dict


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
MAIN_GATE_ZONES = [RESTRICTED_ZONE, CROWD_ZONE]
