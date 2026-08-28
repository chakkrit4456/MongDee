"""Lightweight per-camera person tracker — ephemeral IDs only.

Not re-identification: a track ID persists only while a person stays
continuously visible (matched frame-to-frame) in one camera's feed. Leaving
the frame and coming back always starts a new ID, and the same physical
person seen by two different cameras gets two independent IDs. This is a
deliberate, documented limitation (there is no face/person re-id in this
codebase) — good enough for "how many people are on screen right now" and
"which track picked up this product", not for cross-camera or cross-visit
identity.

Matching is greedy IoU, no Kalman filter / SORT — overkill for a few boxes
per frame at this detection rate.
"""

from __future__ import annotations

import time

TRACK_MAX_AGE_SEC = 1.5   # wall-clock: inference cadence varies with cross-camera lock contention
MIN_MATCH_IOU = 0.25


def _iou(box_a, box_b) -> float:
    ax1, ay1, ax2, ay2 = box_a
    bx1, by1, bx2, by2 = box_b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    if ix2 <= ix1 or iy2 <= iy1:
        return 0.0
    inter = (ix2 - ix1) * (iy2 - iy1)
    area_a = (ax2 - ax1) * (ay2 - ay1)
    area_b = (bx2 - bx1) * (by2 - by1)
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


class PersonTracker:
    """One instance per camera. Call update() once per inference frame, even
    with an empty box list, so stale tracks age out promptly."""

    def __init__(self):
        self._tracks: dict[int, dict] = {}  # track_id -> {"bbox", "first_seen", "last_seen"}
        self._next_id = 1

    def update(self, person_boxes: list[list[float]]) -> tuple[list[dict], list[dict]]:
        """Returns (visible_tracks, evicted_tracks).

        visible_tracks: one entry per input box —
          {"track_id", "bbox", "first_seen", "last_seen"}
        evicted_tracks: tracks not re-matched for TRACK_MAX_AGE_SEC, one-shot —
          {"track_id", "first_seen", "last_seen"}
        """
        now = time.time()

        pairs = []
        for track_id, track in self._tracks.items():
            for box_idx, box in enumerate(person_boxes):
                score = _iou(track["bbox"], box)
                if score >= MIN_MATCH_IOU:
                    pairs.append((score, track_id, box_idx))
        pairs.sort(key=lambda p: p[0], reverse=True)

        matched_tracks: set[int] = set()
        matched_boxes: set[int] = set()
        box_to_track: dict[int, int] = {}
        for _score, track_id, box_idx in pairs:
            if track_id in matched_tracks or box_idx in matched_boxes:
                continue
            matched_tracks.add(track_id)
            matched_boxes.add(box_idx)
            box_to_track[box_idx] = track_id

        visible_tracks = []
        for box_idx, box in enumerate(person_boxes):
            track_id = box_to_track.get(box_idx)
            if track_id is None:
                track_id = self._next_id
                self._next_id += 1
                self._tracks[track_id] = {"bbox": box, "first_seen": now, "last_seen": now}
            else:
                track = self._tracks[track_id]
                track["bbox"] = box
                track["last_seen"] = now
            track = self._tracks[track_id]
            visible_tracks.append({
                "track_id": track_id,
                "bbox": box,
                "first_seen": track["first_seen"],
                "last_seen": track["last_seen"],
            })

        evicted_tracks = []
        for track_id in list(self._tracks.keys()):
            if track_id in matched_tracks:
                continue
            track = self._tracks[track_id]
            if now - track["last_seen"] > TRACK_MAX_AGE_SEC:
                evicted_tracks.append({
                    "track_id": track_id,
                    "first_seen": track["first_seen"],
                    "last_seen": track["last_seen"],
                })
                del self._tracks[track_id]

        return visible_tracks, evicted_tracks
