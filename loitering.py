"""
loitering.py — Position-based loitering tracker.

Problem with ID-keyed approach
-------------------------------
YOLO trackers frequently reassign IDs when a person is briefly occluded.
Keying loitering timers by track_id means:
- Timer resets on every ID switch even if the person never left the zone.
- Duplicate loitering alerts fire for one physical person.

Solution: spatial association
------------------------------
We track *positions inside a zone*, not track IDs.

A ZoneSlot represents a person-shaped region inside a zone.
When a new detection arrives we find the nearest existing slot within
SPATIAL_THRESHOLD pixels.  If found we update that slot (extending its
timer without resetting it). If not found we create a new slot.

A slot is expired if no detection has updated it for GRACE_PERIOD_S seconds.

This tolerates:
- ID switches during short occlusions (the position matches the same slot).
- Brief disappearances (grace period prevents premature deletion).

Known limitation (documented)
-------------------------------
If two people are very close together inside the zone and their foot-points
are within SPATIAL_THRESHOLD of each other, their timers may merge into one
slot.  This is acceptable for a low-resolution prototype.
"""

import time
import math
from dataclasses import dataclass, field
from typing import Optional, Set


# Maximum pixel distance to associate a new detection with an existing slot.
SPATIAL_THRESHOLD = 80   # pixels

# How long a slot survives without a detection update (seconds).
# Covers brief occlusions / missed frames.
GRACE_PERIOD_S = 5.0


@dataclass
class ZoneSlot:
    """
    Represents a tracked position inside a monitoring zone.

    Attributes
    ----------
    foot_x, foot_y  : Current foot-point position (pixels).
    first_seen      : Wall-clock time when this slot was first created.
    last_seen       : Wall-clock time of the most recent detection update.
    track_ids_seen  : All tracker IDs that have ever updated this slot
                      (informational — not used for matching).
    loitering_logged: True once a loitering incident has been recorded,
                      preventing duplicate alerts for the same stay.
    """

    foot_x: int
    foot_y: int
    first_seen: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    track_ids_seen: Set[int] = field(default_factory=set)
    loitering_logged: bool = False

    def update(self, foot_x: int, foot_y: int, track_id: Optional[int] = None):
        """Move the slot to the new position and refresh last_seen."""
        self.foot_x = foot_x
        self.foot_y = foot_y
        self.last_seen = time.time()
        if track_id is not None:
            self.track_ids_seen.add(track_id)

    @property
    def elapsed_seconds(self) -> float:
        """Total time this slot has been continuously occupied (seconds)."""
        return time.time() - self.first_seen

    def is_expired(self) -> bool:
        """Return True if no detection has updated this slot recently."""
        return (time.time() - self.last_seen) > GRACE_PERIOD_S

    def distance_to(self, x: int, y: int) -> float:
        return math.hypot(self.foot_x - x, self.foot_y - y)

    def representative_id(self) -> Optional[int]:
        """Return the most recently observed track ID if any."""
        if self.track_ids_seen:
            return max(self.track_ids_seen)  # Not guaranteed, but reasonable
        return None


class LoiteringTracker:
    """
    Manages all ZoneSlots for a single monitoring zone.

    Usage (inside the frame loop)
    ------------------------------
    1. Call update_detections() with the list of foot-points in this zone.
    2. Call get_loitering_slots() to retrieve slots that crossed the threshold.
    3. After logging, call mark_loitering_logged(slot) so it is not re-logged.
    4. Call purge_expired() to remove stale slots.
    """

    def __init__(self, loiter_threshold_s: float = 15.0):
        self.loiter_threshold_s = loiter_threshold_s
        self.slots: list[ZoneSlot] = []

    def update_detections(self, detections: list):
        """
        Associate each detection with an existing slot or create a new one.

        Parameters
        ----------
        detections : list of (foot_x, foot_y, track_id_or_None) tuples
        """
        matched_slots = set()

        for foot_x, foot_y, track_id in detections:
            best_slot = None
            best_dist = float("inf")

            for slot in self.slots:
                d = slot.distance_to(foot_x, foot_y)
                if d < best_dist and d <= SPATIAL_THRESHOLD:
                    best_dist = d
                    best_slot = slot

            if best_slot is not None:
                best_slot.update(foot_x, foot_y, track_id)
                matched_slots.add(id(best_slot))
            else:
                new_slot = ZoneSlot(foot_x=foot_x, foot_y=foot_y)
                if track_id is not None:
                    new_slot.track_ids_seen.add(track_id)
                self.slots.append(new_slot)

    def purge_expired(self):
        """Remove slots that have not been updated within the grace period."""
        self.slots = [s for s in self.slots if not s.is_expired()]

    def get_loitering_slots(self) -> list:
        """Return slots that have exceeded the loitering threshold."""
        return [
            s for s in self.slots
            if s.elapsed_seconds >= self.loiter_threshold_s
        ]

    def get_unlogged_loitering_slots(self) -> list:
        """Return loitering slots that have not yet been logged."""
        return [
            s for s in self.get_loitering_slots()
            if not s.loitering_logged
        ]

    def mark_loitering_logged(self, slot: ZoneSlot):
        """Mark a slot so its loitering event is not logged again."""
        slot.loitering_logged = True

    @property
    def active_count(self) -> int:
        """Number of currently tracked positions (people) in the zone."""
        return len(self.slots)
