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


def laser_on(timeout: float = 5.0) -> requests.Response:
    url = f"{_base_url()}/laser/on"
    return requests.post(url, timeout=timeout)


def laser_off(timeout: float = 5.0) -> requests.Response:
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
    return requests.post(url, json=payload, timeout=timeout)


def get_motion_config(timeout: float = 5.0) -> Dict[str, Any]:
    url = f"{_base_url()}/config/motion"
    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def update_motion_config(
    x_min: Optional[float] = None,
    x_max: Optional[float] = None,
    y_min: Optional[float] = None,
    y_max: Optional[float] = None,
    z_min: Optional[float] = None,
    z_max: Optional[float] = None,
    neutral_x: Optional[float] = None,
    neutral_y: Optional[float] = None,
    neutral_z: Optional[float] = None,
    travel_speed: Optional[float] = None,
    z_speed: Optional[float] = None,
    send_rate_hz: Optional[float] = None,
    feedrate_multiplier: Optional[float] = None,
    timeout: float = 5.0,
) -> requests.Response:
    """POST /config/motion — only non-None fields are sent (MotionConfigUpdate)."""
    url = f"{_base_url()}/config/motion"
    payload: Dict[str, Any] = {}
    pairs: list[tuple[str, Optional[float]]] = [
        ("x_min", x_min),
        ("x_max", x_max),
        ("y_min", y_min),
        ("y_max", y_max),
        ("z_min", z_min),
        ("z_max", z_max),
        ("neutral_x", neutral_x),
        ("neutral_y", neutral_y),
        ("neutral_z", neutral_z),
        ("travel_speed", travel_speed),
        ("z_speed", z_speed),
        ("send_rate_hz", send_rate_hz),
        ("feedrate_multiplier", feedrate_multiplier),
    ]
    for key, val in pairs:
        if val is not None:
            payload[key] = val
    return requests.post(url, json=payload, timeout=timeout)


def push_local_config_to_jetson(
    cfg: Any,
    timeout: float = 10.0,
) -> tuple[requests.Response, requests.Response]:
    """
    POST current network + motion from an AppConfig-like object to the Jetson.
    Sends all network fields (moonraker_*, esp32) and all motion floats so the
    server matches the saved form.
    """
    net_resp = update_network_config(
        moonraker_host=cfg.moonraker_host,
        moonraker_port=cfg.moonraker_port,
        moonraker_path=cfg.moonraker_path,
        esp32_ip=cfg.esp32_ip,
        timeout=timeout,
    )
    mot_resp = update_motion_config(
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
        z_speed=cfg.z_speed,
        send_rate_hz=cfg.send_rate_hz,
        feedrate_multiplier=cfg.feedrate_multiplier,
        timeout=timeout,
    )
    return net_resp, mot_resp


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
        description="Jetson API: fetch config and print JSON to the terminal.",
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
        help="GET /config/motion (limits, neutrals, speeds, send_rate_hz, …).",
    )

    args = parser.parse_args()
    if args.command != "get":
        parser.error("unknown command")

    try:
        base = _base_url()
        if args.resource == "network":
            path = "/config/network"
            data = get_network_config()
        else:
            path = "/config/motion"
            data = get_motion_config()
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

