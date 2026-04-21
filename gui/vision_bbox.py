"""Parse GET /vision/detection JSON for bbox overlay (shared by video UI)."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple


def _frame_size_from_detection(data: Dict[str, Any]) -> tuple[float, float]:
    fw = data.get("frame_width") or data.get("camera_width")
    fh = data.get("frame_height") or data.get("camera_height")
    if fw is None:
        fw = 1920
    if fh is None:
        fh = 1080
    return float(fw), float(fh)


def outline_color_for_track(class_name: Any, class_id: Any) -> str:
    """Person → green, goose/bird → red; COCO ids 0 / 14; other classes → yellow."""
    n = str(class_name).strip().lower() if class_name is not None else ""
    if n == "person":
        return "#00cc00"
    if n in ("goose", "geese") or "goose" in n:
        return "red"
    try:
        cid = int(class_id)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        cid = None
    if cid == 0:
        return "#00cc00"
    if n == "bird" or "bird" in n:
        return "red"
    if cid == 14:
        return "red"
    return "#cccc00"


def parse_overlay_boxes(
    data: Dict[str, Any],
) -> Tuple[List[Tuple[float, float, float, float, str, bool]], float, float]:
    """
    Multi-track / multi-detection overlay: list of (x, y, w, h, outline_color, is_active).

    Prefers ``tracks`` with ``bbox`` as [x1,y1,x2,y2]; falls back to legacy single bbox.
    """
    fw, fh = _frame_size_from_detection(data)
    active_id = data.get("active_object_id")
    active_track = data.get("active_track")
    tracks = data.get("tracks")
    if isinstance(tracks, list) and tracks:
        out: List[Tuple[float, float, float, float, str, bool]] = []
        for t in tracks:
            if not isinstance(t, dict):
                continue
            bbox = t.get("bbox")
            if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
                continue
            x1, y1, x2, y2 = (float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3]))
            w, h = x2 - x1, y2 - y1
            cls = t.get("class")
            cid = t.get("class_id")
            color = outline_color_for_track(cls, cid)
            oid = t.get("object_id")
            is_active = active_id is not None and oid is not None and active_id == oid
            out.append((x1, y1, w, h, color, is_active))
        if out:
            return out, fw, fh

    # If multi-track isn't present, try object list detections (multi-class, multi-object).
    dets = data.get("detections")
    if isinstance(dets, list) and dets:
        out2: List[Tuple[float, float, float, float, str, bool]] = []
        for d in dets:
            if not isinstance(d, dict):
                continue
            bbox = d.get("bbox")
            if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
                continue
            x1, y1, x2, y2 = (
                float(bbox[0]),
                float(bbox[1]),
                float(bbox[2]),
                float(bbox[3]),
            )
            w, h = x2 - x1, y2 - y1
            cls = d.get("class_name", d.get("class"))
            cid = d.get("class_id")
            color = outline_color_for_track(cls, cid)
            out2.append((x1, y1, w, h, color, False))
        if out2:
            # If the endpoint also provides active_track, mark it as active by bbox match.
            if isinstance(active_track, dict):
                ab = active_track.get("bbox")
                if isinstance(ab, (list, tuple)) and len(ab) == 4:
                    ax1, ay1, ax2, ay2 = (float(ab[0]), float(ab[1]), float(ab[2]), float(ab[3]))
                    for i, (x1, y1, w, h, color, _active) in enumerate(out2):
                        if x1 == ax1 and y1 == ay1 and (x1 + w) == ax2 and (y1 + h) == ay2:
                            out2[i] = (x1, y1, w, h, color, True)
                            break
            return out2, fw, fh

    box, fw2, fh2 = parse_bbox_and_frame(data)
    if box is not None:
        return [(*box, "red", True)], fw2, fh2
    return [], fw, fh


def parse_bbox_and_frame(
    data: Dict[str, Any],
) -> Tuple[Optional[Tuple[float, float, float, float]], float, float]:
    """
    Returns ((x, y, w, h) in frame pixel space or normalized), frame_width, frame_height.
    If has_target is False or bbox missing, returns (None, fw, fh).
    """
    fw, fh = _frame_size_from_detection(data)
    if data.get("has_target") is False:
        return None, fw, fh

    det = data.get("detection")
    if isinstance(det, dict):
        b = det.get("bbox") or det.get("box")
    else:
        b = None
    if b is None:
        b = data.get("bbox") or data.get("box") or data.get("rect")

    if b is None and all(k in data for k in ("x1", "y1", "x2", "y2")):
        x1, y1 = float(data["x1"]), float(data["y1"])
        x2, y2 = float(data["x2"]), float(data["y2"])
        return (x1, y1, x2 - x1, y2 - y1), fw, fh

    if b is None:
        return None, fw, fh

    if isinstance(b, (list, tuple)) and len(b) == 4:
        a, c, d, e = (float(x) for x in b)
        if max(abs(a), abs(c), abs(d), abs(e)) <= 1.0:
            return (a * fw, c * fh, d * fw, e * fh), fw, fh
        # Legacy ambiguity: some servers send [x, y, w, h] while others send [x1, y1, x2, y2].
        # Heuristic: treat as xyxy when it looks like corners within frame bounds.
        looks_like_xyxy = (
            d >= a
            and e >= c
            and fw > 0
            and fh > 0
            and d <= fw
            and e <= fh
            and (d - a) <= fw
            and (e - c) <= fh
        )
        if looks_like_xyxy:
            return (a, c, d - a, e - c), fw, fh
        return (a, c, d, e), fw, fh
    if isinstance(b, dict):
        if all(k in b for k in ("x1", "y1", "x2", "y2")):
            x1, y1 = float(b["x1"]), float(b["y1"])
            x2, y2 = float(b["x2"]), float(b["y2"])
            return (x1, y1, x2 - x1, y2 - y1), fw, fh
        x0 = b.get("x", b.get("left"))
        y0 = b.get("y", b.get("top"))
        w0 = b.get("w", b.get("width"))
        h0 = b.get("h", b.get("height"))
        if x0 is None or y0 is None:
            return None, fw, fh
        x0, y0 = float(x0), float(y0)
        if w0 is not None and h0 is not None:
            return (x0, y0, float(w0), float(h0)), fw, fh
        x1 = b.get("x2", b.get("right"))
        y1 = b.get("y2", b.get("bottom"))
        if x1 is not None and y1 is not None:
            return (x0, y0, float(x1) - x0, float(y1) - y0), fw, fh
    return None, fw, fh
