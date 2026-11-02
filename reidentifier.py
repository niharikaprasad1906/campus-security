"""
reidentifier.py — Lightweight Re-Identification layer for campus-security.

Problem
-------
YOLO trackers (BoT-SORT, ByteTrack) frequently reassign track IDs when a
person is briefly occluded at 10 FPS.  The same physical person then appears
with a new ID, triggering repeated loitering/intrusion alerts.

Solution: appearance gallery
-----------------------------
We maintain a *gallery* of recently seen people keyed by a stable
*canonical ID* that we assign ourselves.  Each gallery entry stores:
  - Last known foot-point position
  - An HSV colour histogram of the person's torso region
  - When the entry was last updated

When the YOLO tracker assigns a brand-new raw ID, we compare the new
detection against the gallery by two criteria:
  1. Spatial proximity  (< SPATIAL_THRESH pixels from last known position)
  2. Appearance similarity (histogram correlation ≥ APPEARANCE_THRESH)

If both match, the new raw ID is remapped to the existing canonical ID.
Otherwise a new canonical ID is created.

Honest limitations (low-resolution footage, 10 FPS)
----------------------------------------------------
- Colour histograms are less discriminative at 768×576; two people in
  similar clothing can be merged.
- Gallery age is capped at MAX_GALLERY_AGE_S (default 8 s).  Occlusions
  longer than that always produce a new canonical ID.
- This is heuristic matching.  It reduces duplicate IDs; it does NOT
  guarantee perfect identity persistence.
- We do NOT use facial features or deep-learning ReID models, in line
  with the project's privacy guidelines.
"""

import cv2
import numpy as np
import time
import math
from dataclasses import dataclass, field
from typing import Dict, Optional

# ── Tuning parameters ─────────────────────────────────────────────────────────
# Maximum pixel distance between last known position and new detection.
SPATIAL_THRESH = 120

# Minimum histogram correlation to accept an appearance match.
# cv2.HISTCMP_CORREL ranges -1 (inverse) → 0 (no relation) → 1 (perfect).
APPEARANCE_THRESH = 0.55

# How long a lost track stays in the gallery before being discarded (seconds).
MAX_GALLERY_AGE_S = 8.0
# ──────────────────────────────────────────────────────────────────────────────


def _extract_histogram(frame: np.ndarray, x1: int, y1: int,
                        x2: int, y2: int) -> Optional[np.ndarray]:
    """
    Return a normalised HSV colour histogram of the upper 2/3 of the
    bounding box (torso region — more distinctive than legs).

    Returns None if the crop is empty or invalid.
    """
    h, w = frame.shape[:2]
    x1 = max(0, x1)
    y1 = max(0, y1)
    x2 = min(w - 1, x2)
    y2 = min(h - 1, y2)

    if x2 <= x1 or y2 <= y1:
        return None

    crop = frame[y1:y2, x1:x2]
    if crop.size == 0:
        return None

    # Keep only the upper 2/3 (ignore feet / ground reflections).
    upper_h = max(1, int(crop.shape[0] * 0.67))
    crop = crop[:upper_h]

    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    # 18 hue bins × 8 saturation bins — coarse enough to be robust to
    # lighting variation, fine enough to separate distinct clothing colours.
    hist = cv2.calcHist([hsv], [0, 1], None, [18, 8], [0, 180, 0, 256])
    cv2.normalize(hist, hist)
    return hist.flatten()


@dataclass
class GalleryEntry:
    """Record for one canonical person in the gallery."""

    canonical_id: int
    foot_x: int
    foot_y: int
    histogram: Optional[np.ndarray]
    last_seen: float = field(default_factory=time.time)

    def distance_to(self, x: int, y: int) -> float:
        return math.hypot(self.foot_x - x, self.foot_y - y)

    def appearance_similarity(self, hist: Optional[np.ndarray]) -> float:
        """Return histogram correlation in [−1, 1]; 0 if either hist is None."""
        if self.histogram is None or hist is None:
            return 0.0
        return float(cv2.compareHist(
            self.histogram.reshape(-1, 1).astype(np.float32),
            hist.reshape(-1, 1).astype(np.float32),
            cv2.HISTCMP_CORREL,
        ))

    def update(self, foot_x: int, foot_y: int,
               histogram: Optional[np.ndarray]):
        self.foot_x = foot_x
        self.foot_y = foot_y
        self.last_seen = time.time()
        if histogram is not None:
            self.histogram = histogram

    def is_expired(self) -> bool:
        return (time.time() - self.last_seen) > MAX_GALLERY_AGE_S


class ReIdentifier:
    """
    Maps unstable raw YOLO tracker IDs to stable canonical person IDs.

    Usage (per frame)
    -----------------
    1. For every detected person box call ``get_canonical_id()``.
    2. Use the returned canonical ID everywhere (loitering, logging, display).
    3. At the very end of the frame call ``end_frame(active_raw_ids)`` so the
       gallery knows which raw IDs have disappeared.

    The gallery is pruned automatically; no manual maintenance required.
    """

    def __init__(self):
        # raw_id  → canonical_id   (only for currently visible detections)
        self._id_map: Dict[int, int] = {}
        # canonical_id → GalleryEntry  (active + recently lost)
        self._gallery: Dict[int, GalleryEntry] = {}
        self._next_cid: int = 1

    # ── Public API ─────────────────────────────────────────────────────────

    def get_canonical_id(
        self,
        raw_id: int,
        foot_x: int,
        foot_y: int,
        frame: Optional[np.ndarray] = None,
        x1: int = 0,
        y1: int = 0,
        x2: int = 0,
        y2: int = 0,
    ) -> int:
        """
        Return the canonical ID for a detection.

        Parameters
        ----------
        raw_id  : Track ID assigned by YOLO tracker this frame.
        foot_x, foot_y : Bottom-centre foot-point of the bounding box.
        frame   : Current BGR frame (for histogram extraction).
                  Pass None to disable appearance matching (spatial-only).
        x1,y1,x2,y2 : Bounding box coordinates (for histogram crop).
        """
        hist = _extract_histogram(frame, x1, y1, x2, y2) if frame is not None else None

        # ── Case 1: raw_id already mapped this session ──────────────────
        if raw_id in self._id_map:
            cid = self._id_map[raw_id]
            if cid in self._gallery:
                self._gallery[cid].update(foot_x, foot_y, hist)
            return cid

        # ── Case 2: new raw_id — search gallery for a match ─────────────
        best_cid: Optional[int] = None
        best_score: float = -999.0

        for cid, entry in self._gallery.items():
            # Skip entries already claimed by an active raw_id.
            if cid in self._id_map.values():
                continue

            dist = entry.distance_to(foot_x, foot_y)
            if dist > SPATIAL_THRESH:
                continue

            app_sim = entry.appearance_similarity(hist)

            if hist is not None and entry.histogram is not None:
                # Require appearance threshold when both histograms exist.
                if app_sim < APPEARANCE_THRESH:
                    continue
                # Combined score: appearance dominates, distance is a tiebreaker.
                score = app_sim - (dist / SPATIAL_THRESH) * 0.2
            else:
                # No histogram on one side — fall back to spatial-only with
                # a tighter distance requirement (half the normal threshold).
                if dist > SPATIAL_THRESH * 0.5:
                    continue
                score = 1.0 - (dist / (SPATIAL_THRESH * 0.5))

            if score > best_score:
                best_score = score
                best_cid = cid

        if best_cid is not None:
            # ── Re-identified: reuse the existing canonical ID ───────────
            self._gallery[best_cid].update(foot_x, foot_y, hist)
            self._id_map[raw_id] = best_cid
            return best_cid

        # ── Case 3: genuinely new person ────────────────────────────────
        new_cid = self._next_cid
        self._next_cid += 1
        self._gallery[new_cid] = GalleryEntry(
            canonical_id=new_cid,
            foot_x=foot_x,
            foot_y=foot_y,
            histogram=hist,
        )
        self._id_map[raw_id] = new_cid
        return new_cid

    def end_frame(self, active_raw_ids: set):
        """
        Call at the end of every frame with the set of raw IDs visible
        this frame.  Removes stale id_map entries and prunes expired
        gallery entries.
        """
        # Drop raw IDs that are no longer being tracked.
        stale_raw = set(self._id_map.keys()) - active_raw_ids
        for rid in stale_raw:
            del self._id_map[rid]

        # Remove gallery entries that have aged out.
        expired = [cid for cid, e in self._gallery.items() if e.is_expired()]
        for cid in expired:
            del self._gallery[cid]

    # ── Diagnostics ────────────────────────────────────────────────────────

    @property
    def gallery_size(self) -> int:
        return len(self._gallery)

    @property
    def active_mappings(self) -> int:
        return len(self._id_map)
