from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Dict, Optional

import requests

from config import get_config


def _base_url() -> str:
    cfg = get_config()
    return f"http://{cfg.jetson_ip}:{cfg.api_port}"


def post_handshake(client_ip: str, timeout: float = 5.0) -> requests.Response:
    """POST /system/handshake with JSON {\"client_ip\": \"<ipv4>\"}."""
    url = f"{_base_url()}/system/handshake"
    return requests.post(url, json={"client_ip": client_ip}, timeout=timeout)


def jetson_ip_from_handshake_response(resp: requests.Response) -> Optional[str]:
    """
    If the handshake JSON body includes the Jetson's address, return it so we can
    persist config. Tries: jetson_ip, server_ip, device_ip, host_ip, jetson.
    """
    try:
        data = resp.json()
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    for key in ("jetson_ip", "server_ip", "device_ip", "host_ip", "jetson"):
        val = data.get(key)
        if val is not None and str(val).strip():
            return str(val).strip()
    return None


def start_tracking(timeout: float = 5.0) -> requests.Response:
    url = f"{_base_url()}/start_tracking"
    return requests.post(url, timeout=timeout)


def stop_tracking(timeout: float = 5.0) -> requests.Response:
    url = f"{_base_url()}/stop_tracking"
    return requests.post(url, timeout=timeout)


def move_laser(x: float, y: float, timeout: float = 5.0) -> requests.Response:
    url = f"{_base_url()}/move_laser"
    payload = {"x": float(x), "y": float(y)}
    return requests.post(url, json=payload, timeout=timeout)


def move_z(delta_mm: float, velocity: float = 2.0, timeout: float = 5.0) -> requests.Response:
    """
    Move Z axis by a relative delta in millimeters, with a given velocity.

    This will send a payload that conceptually corresponds to a command like:
    `Move_Z D=1.00 V=2`
    """
    url = f"{_base_url()}/z/move"
    # Match the FastAPI contract:
    # - default: {"delta_mm": 1.0}
    # - custom V: {"delta_mm": 1.0, "velocity": 5.5}
    payload: Dict[str, Any] = {"delta_mm": float(delta_mm)}
    # Only include velocity if it was explicitly provided / differs from default
    if velocity is not None:
        payload["velocity"] = float(velocity)
    return requests.post(url, json=payload, timeout=timeout)


def laser_status(timeout: float = 5.0) -> requests.Response:
    """GET /laser/status — current laser / ESP32-side state from the Jetson."""
    url = f"{_base_url()}/laser/status"
    return requests.get(url, timeout=timeout)


def laser_on(timeout: float = 5.0) -> requests.Response:
    """POST /laser/on"""
    url = f"{_base_url()}/laser/on"
    return requests.post(url, timeout=timeout)


def laser_off(timeout: float = 5.0) -> requests.Response:
    """POST /laser/off"""
    url = f"{_base_url()}/laser/off"
    return requests.post(url, timeout=timeout)


def get_network_config(timeout: float = 5.0) -> Dict[str, Any]:
    url = f"{_base_url()}/config/network"
    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def update_network_config(
    moonraker_host: Optional[str] = None,
    moonraker_port: Optional[int] = None,
    moonraker_path: Optional[str] = None,
    esp32_ip: Optional[str] = None,
    laptop_ip: Optional[str] = None,
    stream_port: Optional[int] = None,
    timeout: float = 5.0,
) -> requests.Response:
    """POST /config/network — NetworkConfigUpdate; only non-None fields are sent."""
    url = f"{_base_url()}/config/network"
    payload: Dict[str, Any] = {}
    if moonraker_host is not None:
        payload["moonraker_host"] = moonraker_host
    if moonraker_port is not None:
        payload["moonraker_port"] = moonraker_port
    if moonraker_path is not None:
        payload["moonraker_path"] = moonraker_path
    if esp32_ip is not None:
        payload["esp32_ip"] = esp32_ip
    if laptop_ip is not None:
        payload["laptop_ip"] = laptop_ip
    if stream_port is not None:
        payload["stream_port"] = stream_port
    return requests.post(url, json=payload, timeout=timeout)


def get_motion_config(timeout: float = 5.0) -> Dict[str, Any]:
    url = f"{_base_url()}/config/motion"
    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


# Keys accepted by POST /config/motion (partial update — only sent fields change).
_MOTION_POST_KEYS = frozenset(
    {
        "x_min",
        "x_max",
        "y_min",
        "y_max",
        "z_min",
        "z_max",
        "neutral_x",
        "neutral_y",
        "neutral_z",
        "travel_speed",
        "move_z_velocity",
        "camera_width",
        "camera_height",
        "detection_confidence_threshold",
        "tracking_kp",
        "tracking_ki",
        "tracking_integral_max_px",
        "tracking_deadzone_px",
        "tracking_min_step_mm",
        "tracking_max_step_mm",
        "tracking_target_lost_frames",
        "search_step_mm",
        "vision_staleness_s",
    }
)


def update_motion_config(timeout: float = 5.0, **kwargs: Any) -> requests.Response:
    """POST /config/motion — partial update; only known keys with non-None values are sent."""
    url = f"{_base_url()}/config/motion"
    payload: Dict[str, Any] = {}
    for key, val in kwargs.items():
        if key in _MOTION_POST_KEYS and val is not None:
            payload[key] = val
    return requests.post(url, json=payload, timeout=timeout)


def get_system_network(timeout: float = 5.0) -> Dict[str, Any]:
    """GET /system/network — Jetson IP, peer, stream port, control_api_port, …"""
    url = f"{_base_url()}/system/network"
    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def get_vision_detection(timeout: float = 5.0) -> Dict[str, Any]:
    """
    GET /vision/detection — legacy single bbox and/or multi-object ``tracks``,
    ``active_object_id``, ``frame_id``, ``timestamp``, frame size (overlay).
    """
    url = f"{_base_url()}/vision/detection"
    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def get_vision_classes_config(timeout: float = 5.0) -> Dict[str, Any]:
    """GET /config/vision/classes — include, exclude, class_thresholds (shape matches POST)."""
    url = f"{_base_url()}/config/vision/classes"
    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def update_vision_classes_config(
    include: Optional[list[int]] = None,
    exclude: Optional[list[int]] = None,
    class_thresholds: Optional[Dict[str, float]] = None,
    timeout: float = 5.0,
) -> requests.Response:
    """POST /config/vision/classes — partial body; only non-None keys are sent."""
    url = f"{_base_url()}/config/vision/classes"
    body: Dict[str, Any] = {}
    if include is not None:
        body["include"] = list(include)
    if exclude is not None:
        body["exclude"] = list(exclude)
    if class_thresholds is not None:
        body["class_thresholds"] = dict(class_thresholds)
    return requests.post(url, json=body, timeout=timeout)


def get_detection_config(timeout: float = 5.0) -> Dict[str, Any]:
    """GET /config/detection — arbitrary JSON for Detection (merged into local config)."""
    url = f"{_base_url()}/config/detection"
    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def update_detection_config(
    updates: Optional[Dict[str, Any]] = None,
    timeout: float = 5.0,
) -> requests.Response:
    """POST /config/detection — body is the detection object (full replace or partial per server)."""
    url = f"{_base_url()}/config/detection"
    body: Dict[str, Any] = dict(updates) if updates is not None else {}
    return requests.post(url, json=body, timeout=timeout)


def push_local_config_to_jetson(
    cfg: Any,
    timeout: float = 10.0,
) -> tuple[
    requests.Response, requests.Response, requests.Response, requests.Response
]:
    """
    POST network, motion, detection, and vision class policy from an AppConfig-like object.
    """
    net_resp = update_network_config(
        moonraker_host=cfg.moonraker_host,
        moonraker_port=cfg.moonraker_port,
        moonraker_path=cfg.moonraker_path,
        esp32_ip=cfg.esp32_ip,
        laptop_ip=(cfg.laptop_ip.strip() or None),
        stream_port=cfg.camera_port,
        timeout=timeout,
    )
    mot_resp = update_motion_config(
        timeout=timeout,
        x_min=cfg.x_min,
        x_max=cfg.x_max,
        y_min=cfg.y_min,
        y_max=cfg.y_max,
        z_min=cfg.z_min,
        z_max=cfg.z_max,
        neutral_x=cfg.neutral_x,
        neutral_y=cfg.neutral_y,
        neutral_z=cfg.neutral_z,
        travel_speed=cfg.travel_speed,
        move_z_velocity=cfg.move_z_velocity,
        camera_width=cfg.camera_width,
        camera_height=cfg.camera_height,
        detection_confidence_threshold=cfg.detection_confidence_threshold,
        tracking_kp=cfg.tracking_kp,
        tracking_ki=cfg.tracking_ki,
        tracking_integral_max_px=cfg.tracking_integral_max_px,
        tracking_deadzone_px=cfg.tracking_deadzone_px,
        tracking_min_step_mm=cfg.tracking_min_step_mm,
        tracking_max_step_mm=cfg.tracking_max_step_mm,
        tracking_target_lost_frames=cfg.tracking_target_lost_frames,
        search_step_mm=cfg.search_step_mm,
        vision_staleness_s=cfg.vision_staleness_s,
    )
    det_resp = update_detection_config(cfg.detection, timeout=timeout)
    vis_resp = update_vision_classes_config(
        include=list(cfg.vision_classes_include),
        exclude=list(cfg.vision_classes_exclude),
        class_thresholds=dict(cfg.vision_class_thresholds),
        timeout=timeout,
    )
    return net_resp, mot_resp, det_resp, vis_resp


def camera_stream_url() -> str:
    """
    Returns the MJPEG camera stream URL that you can paste into a browser.
    Example: http://<JETSON_IP>:8000/video
    """
    cfg = get_config()
    return f"http://{cfg.jetson_ip}:{cfg.camera_port}/video"


def emergency_stop(timeout: float = 5.0) -> requests.Response:
    url = f"{_base_url()}/emergency_stop"
    return requests.post(url, timeout=timeout)


def firmware_restart(timeout: float = 5.0) -> requests.Response:
    url = f"{_base_url()}/firmware_restart"
    return requests.post(url, timeout=timeout)


def klipper_restart(timeout: float = 5.0) -> requests.Response:
    url = f"{_base_url()}/klipper_restart"
    return requests.post(url, timeout=timeout)


def tmc_dump(stepper: str, timeout: float = 5.0) -> requests.Response:
    """
    Request TMC diagnostics for a given stepper, e.g. 'stepper_z', 'stepper_x', 'stepper_y'.
    """
    url = f"{_base_url()}/tmc/dump"
    payload = {"stepper": stepper}
    return requests.post(url, json=payload, timeout=timeout)


def send_click(
    x: int, y: int, timestamp: float | None = None, timeout: float = 5.0
) -> requests.Response:
    """
    Send click coordinates to the Jetson for distance estimation.

    Uses the same host and api_port as the rest of the Jetson API (see config).

    Args:
        x: X coordinate in pixels (0 to 3840)
        y: Y coordinate in pixels (0 to 2160)
        timestamp: Optional Unix timestamp in seconds. If None, Jetson adds current time.
        timeout: Request timeout in seconds.

    Returns:
        Response object with status and point information.
    """
    url = f"{_base_url()}/click"
    payload: Dict[str, Any] = {"x": int(x), "y": int(y)}
    if timestamp is not None:
        payload["timestamp"] = float(timestamp)
    return requests.post(url, json=payload, timeout=timeout)


def _cli_print_get(url: str, data: Any) -> None:
    print(f"=== GET {url} ===")
    print(json.dumps(data, indent=2, sort_keys=True))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Jetson API: GET/POST config from the terminal.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    get_p = sub.add_parser("get", help="GET a config endpoint (stdout: formatted JSON).")
    get_sub = get_p.add_subparsers(dest="resource", required=True)
    get_sub.add_parser(
        "network",
        help="GET /config/network (Moonraker, ESP32, laptop IP, stream port, …).",
    )
    get_sub.add_parser(
        "motion",
        help="GET /config/motion (limits, neutrals, travel_speed, move_z_velocity, …).",
    )
    get_sub.add_parser(
        "detection",
        help="GET /config/detection (Detection JSON blob).",
    )
    get_sub.add_parser(
        "system-network",
        help="GET /system/network (Jetson IP, peer, stream port, control_api_port, …).",
    )
    get_sub.add_parser(
        "vision-detection",
        help="GET /vision/detection (bbox overlay: has_target, bbox, confidence, …).",
    )
    get_sub.add_parser(
        "vision-classes",
        help="GET /config/vision/classes (include, exclude, class_thresholds).",
    )

    sub.add_parser(
        "push",
        help="POST config to /config/network, /config/motion, /config/detection, /config/vision/classes.",
    )

    args = parser.parse_args()

    if args.command == "push":
        try:
            cfg = get_config()
            net_r, mot_r, det_r, vis_r = push_local_config_to_jetson(cfg)
            net_r.raise_for_status()
            mot_r.raise_for_status()
            base = _base_url()
            print(f"POST {base}/config/network HTTP {net_r.status_code}")
            try:
                print(json.dumps(net_r.json(), indent=2, sort_keys=True))
            except ValueError:
                print(net_r.text)
            print(f"POST {base}/config/motion HTTP {mot_r.status_code}")
            try:
                print(json.dumps(mot_r.json(), indent=2, sort_keys=True))
            except ValueError:
                print(mot_r.text)
            print(f"POST {base}/config/detection HTTP {det_r.status_code}")
            try:
                print(json.dumps(det_r.json(), indent=2, sort_keys=True))
            except ValueError:
                print(det_r.text)
            if det_r.status_code == 404:
                print(
                    "(detection POST returned 404 — route may not be deployed)",
                    file=sys.stderr,
                )
            else:
                det_r.raise_for_status()
            print(f"POST {base}/config/vision/classes HTTP {vis_r.status_code}")
            try:
                print(json.dumps(vis_r.json(), indent=2, sort_keys=True))
            except ValueError:
                print(vis_r.text)
            if vis_r.status_code == 404:
                print(
                    "(vision/classes POST returned 404 — route may not be deployed)",
                    file=sys.stderr,
                )
            else:
                vis_r.raise_for_status()
        except requests.RequestException as exc:
            print(f"HTTP error: {exc}", file=sys.stderr)
            resp = getattr(exc, "response", None)
            if resp is not None:
                print(resp.text, file=sys.stderr)
            raise SystemExit(1) from exc
        except Exception as exc:  # noqa: BLE001
            print(f"Error: {exc}", file=sys.stderr)
            raise SystemExit(1) from exc
        return

    if args.command != "get":
        parser.error("unknown command")

    try:
        base = _base_url()
        if args.resource == "network":
            path = "/config/network"
            data = get_network_config()
        elif args.resource == "motion":
            path = "/config/motion"
            data = get_motion_config()
        elif args.resource == "detection":
            path = "/config/detection"
            data = get_detection_config()
        elif args.resource == "system-network":
            path = "/system/network"
            data = get_system_network()
        elif args.resource == "vision-detection":
            path = "/vision/detection"
            data = get_vision_detection()
        elif args.resource == "vision-classes":
            path = "/config/vision/classes"
            data = get_vision_classes_config()
        else:
            parser.error(f"unknown resource: {args.resource!r}")
        _cli_print_get(f"{base}{path}", data)
    except requests.RequestException as exc:
        print(f"HTTP error: {exc}", file=sys.stderr)
        resp = getattr(exc, "response", None)
        if resp is not None:
            print(resp.text, file=sys.stderr)
        raise SystemExit(1) from exc
    except Exception as exc:  # noqa: BLE001
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()

