"""Per-camera product movement / "interest" tracking.

Implements the rule the booth needs for its Dashboard: a product resting
untouched for STATIONARY_BASELINE_SEC is "not moved" (idle baseline). But as
soon as a person's hand overlaps it and it moves, the 10-second countdown
does not apply — instead the time spent held counts as "interest time" for
that product. When the hold ends, one event is recorded naming which
(ephemeral, see core/tracker.py) person track did the holding.

Deliberately separate from core/aggregator.py: the aggregator answers "what
is THE current product for the whole booth" via cross-camera agreement at
class-name granularity, for the product-info panel. This module answers a
different, inherently per-camera question — bounding boxes and person track
IDs from core/tracker.py are per-camera and not comparable across cameras —
so it is keyed by (camera_id, class_name) instead.
"""

from __future__ import annotations

import threading
import time

STATIONARY_BASELINE_SEC = 10.0     # sit still this long, untouched -> "idle" (not moved)
MOVEMENT_PX_THRESHOLD = 20.0       # centroid displacement vs. resting position, at 640x480 capture
HOLD_MIN_IOU = 0.02                # product bbox overlaps a person bbox at least this much...
RELEASE_GRACE_SEC = 1.0            # ...or stop counting as "held" after this long without contact/movement
PRODUCT_ABSENCE_TIMEOUT_SEC = 3.0  # matches aggregator.IDLE_RESET_SEC
MIN_HOLD_DURATION_SEC = 0.5        # denoise single-frame detection blips

STATE_UNSETTLED = "unsettled"
STATE_IDLE = "idle"
STATE_HELD = "held"


def _centroid(bbox):
    x1, y1, x2, y2 = bbox
    return (x1 + x2) / 2.0, (y1 + y2) / 2.0


def _dist(a, b):
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5


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


def _center_inside(inner_bbox, outer_bbox) -> bool:
    cx, cy = _centroid(inner_bbox)
    x1, y1, x2, y2 = outer_bbox
    return x1 <= cx <= x2 and y1 <= cy <= y2


def _find_holder(product_bbox, person_tracks: list[dict]) -> dict | None:
    best = None
    best_score = 0.0
    for track in person_tracks:
        score = _iou(product_bbox, track["bbox"])
        touching = score >= HOLD_MIN_IOU or _center_inside(product_bbox, track["bbox"])
        if touching and score >= best_score:
            best = track
            best_score = score
    return best


class _ProductState:
    def __init__(self, bbox, now):
        self.state = STATE_UNSETTLED
        self.resting_bbox = bbox
        self.settle_start_ts = now
        self.last_seen_ts = now
        self.hold_start_ts: float | None = None
        self.holder_track_id: int | None = None

    def interest_seconds(self, now) -> float:
        if self.state == STATE_HELD and self.hold_start_ts is not None:
            return now - self.hold_start_ts
        return 0.0


class ProductInterestTracker:
    def __init__(self):
        self._states: dict[tuple[str, str], _ProductState] = {}
        self._lock = threading.Lock()

    def update(self, camera_id: str, product_detections: list[dict],
               person_tracks: list[dict]) -> list[dict]:
        """Call once per inference frame per camera. Returns zero or more
        finalized hold events: {camera_id, class_name, holder_track_id,
        hold_start_ts, hold_end_ts, duration_sec}."""
        now = time.time()
        events = []

        best_by_class: dict[str, dict] = {}
        for det in product_detections:
            name = det["class_name"]
            if name not in best_by_class or det["conf"] > best_by_class[name]["conf"]:
                best_by_class[name] = det

        with self._lock:
            for class_name, det in best_by_class.items():
                key = (camera_id, class_name)
                bbox = det["bbox"]
                state = self._states.get(key)
                if state is None:
                    self._states[key] = _ProductState(bbox, now)
                    continue

                state.last_seen_ts = now
                moved = _dist(_centroid(bbox), _centroid(state.resting_bbox)) > MOVEMENT_PX_THRESHOLD
                holder = _find_holder(bbox, person_tracks)

                if moved and holder is not None:
                    if state.state != STATE_HELD:
                        state.state = STATE_HELD
                        state.hold_start_ts = now
                        state.holder_track_id = holder["track_id"]
                    elif holder["track_id"] != state.holder_track_id:
                        # hand-off: close the current holder's segment, open a new one
                        duration = now - state.hold_start_ts
                        if duration >= MIN_HOLD_DURATION_SEC:
                            events.append({
                                "camera_id": camera_id, "class_name": class_name,
                                "holder_track_id": state.holder_track_id,
                                "hold_start_ts": state.hold_start_ts, "hold_end_ts": now,
                                "duration_sec": duration,
                            })
                        state.hold_start_ts = now
                        state.holder_track_id = holder["track_id"]
                    state.resting_bbox = bbox
                elif state.state == STATE_HELD:
                    if now - state.last_seen_ts >= RELEASE_GRACE_SEC or (not moved and holder is None):
                        duration = now - state.hold_start_ts
                        if duration >= MIN_HOLD_DURATION_SEC:
                            events.append({
                                "camera_id": camera_id, "class_name": class_name,
                                "holder_track_id": state.holder_track_id,
                                "hold_start_ts": state.hold_start_ts, "hold_end_ts": now,
                                "duration_sec": duration,
                            })
                        state.state = STATE_UNSETTLED
                        state.resting_bbox = bbox
                        state.settle_start_ts = now
                        state.hold_start_ts = None
                        state.holder_track_id = None
                elif moved:
                    # displaced without an attributable holder (e.g. nudged) —
                    # can't log an event without a holder, just re-arm the baseline
                    state.resting_bbox = bbox
                    state.settle_start_ts = now
                    state.state = STATE_UNSETTLED
                else:
                    if state.state == STATE_UNSETTLED and now - state.settle_start_ts >= STATIONARY_BASELINE_SEC:
                        state.state = STATE_IDLE

            # drop products not seen recently; finalize an in-progress hold first
            for key in list(self._states.keys()):
                cam, class_name = key
                if cam != camera_id or class_name in best_by_class:
                    continue
                state = self._states[key]
                if now - state.last_seen_ts > PRODUCT_ABSENCE_TIMEOUT_SEC:
                    if state.state == STATE_HELD:
                        duration = state.last_seen_ts - state.hold_start_ts
                        if duration >= MIN_HOLD_DURATION_SEC:
                            events.append({
                                "camera_id": cam, "class_name": class_name,
                                "holder_track_id": state.holder_track_id,
                                "hold_start_ts": state.hold_start_ts, "hold_end_ts": state.last_seen_ts,
                                "duration_sec": duration,
                            })
                    del self._states[key]

        return events

    def live_states(self) -> list[dict]:
        now = time.time()
        with self._lock:
            return [
                {
                    "camera_id": camera_id,
                    "class_name": class_name,
                    "state": state.state,
                    "interest_seconds": state.interest_seconds(now),
                    "holder_track_id": state.holder_track_id,
                }
                for (camera_id, class_name), state in self._states.items()
            ]
