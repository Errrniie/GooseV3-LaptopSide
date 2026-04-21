from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import json
import copy
from typing import Any, Dict, List


@dataclass
class AppConfig:
    """
    Local snapshot of Jetson connection, network, motion, vision/tracking, and detection.
    """

    # Core Jetson connection (laptop → Jetson HTTP)
    jetson_ip: str = "192.168.0.100"
    api_port: int = 8000
    camera_port: int = 5000

    # Network (Moonraker, ESP32, laptop — from API / manual edit)
    moonraker_host: str = "192.168.8.146"
    moonraker_port: int = 7125
    moonraker_path: str = ""
    esp32_ip: str = "192.168.8.186"
    laptop_ip: str = ""

    # Motion + vision / tracking (GET/POST /config/motion; response may use current/updated)
    x_min: float = 0.0
    x_max: float = 11.5
    y_min: float = 0.0
    y_max: float = 7.6
    z_min: float = 0.0
    z_max: float = 7.0
    neutral_x: float = 5.75
    neutral_y: float = 3.8
    neutral_z: float = 3.0
    travel_speed: float = 4000.0
    # MOVE_Z macro V (mm/s or server units); POST /config/motion as move_z_velocity
    move_z_velocity: float = 2.5

    camera_width: int = 1920
    camera_height: int = 1080
    detection_confidence_threshold: float = 0.6
    tracking_kp: float = 0.003
    tracking_ki: float = 0.0
    tracking_integral_max_px: int = 400
    tracking_deadzone_px: int = 30
    tracking_min_step_mm: float = 0.05
    tracking_max_step_mm: float = 3.0
    tracking_target_lost_frames: int = 5
    search_step_mm: float = 1.0
    vision_staleness_s: float = 0.5

    # Last GET /system/network snapshot (Jetson IP, peer, stream port, control_api_port, …)
    system_network: Dict[str, Any] = field(default_factory=dict)

    # GET/POST /config/detection — arbitrary JSON blob
    detection: Dict[str, Any] = field(default_factory=dict)

    # GET/POST /config/vision/classes — YOLO class whitelist + per-class conf thresholds
    vision_classes_include: List[int] = field(default_factory=list)
    vision_classes_exclude: List[int] = field(default_factory=list)
    vision_class_thresholds: Dict[str, float] = field(default_factory=dict)


_CONFIG: AppConfig | None = None


def _default_config_path() -> Path:
    return Path(__file__).with_name("config.json")


def _detection_from_dict(raw: Any) -> Dict[str, Any]:
    if isinstance(raw, dict):
        return copy.deepcopy(raw)
    return {}


def _system_network_from_dict(raw: Any) -> Dict[str, Any]:
    if isinstance(raw, dict):
        return copy.deepcopy(raw)
    return {}


def _int_id_list(raw: Any) -> List[int]:
    if not isinstance(raw, list):
        return []
    out: List[int] = []
    for x in raw:
        try:
            out.append(int(x))
        except (TypeError, ValueError):
            continue
    return out


def _class_thresholds_from_dict(raw: Any) -> Dict[str, float]:
    if not isinstance(raw, dict):
        return {}
    out: Dict[str, float] = {}
    for k, v in raw.items():
        try:
            out[str(k)] = float(v)
        except (TypeError, ValueError):
            continue
    return out


def _config_from_dict(data: Dict[str, Any]) -> AppConfig:
    d = data
    return AppConfig(
        jetson_ip=d.get("jetson_ip", AppConfig.jetson_ip),
        api_port=int(d.get("api_port", AppConfig.api_port)),
        camera_port=int(d.get("camera_port", AppConfig.camera_port)),
        moonraker_host=d.get("moonraker_host", AppConfig.moonraker_host),
        moonraker_port=int(d.get("moonraker_port", AppConfig.moonraker_port)),
        moonraker_path=d.get("moonraker_path", AppConfig.moonraker_path),
        esp32_ip=d.get("esp32_ip", AppConfig.esp32_ip),
        laptop_ip=d.get("laptop_ip", AppConfig.laptop_ip),
        x_min=float(d.get("x_min", AppConfig.x_min)),
        x_max=float(d.get("x_max", AppConfig.x_max)),
        y_min=float(d.get("y_min", AppConfig.y_min)),
        y_max=float(d.get("y_max", AppConfig.y_max)),
        z_min=float(d.get("z_min", AppConfig.z_min)),
        z_max=float(d.get("z_max", AppConfig.z_max)),
        neutral_x=float(d.get("neutral_x", AppConfig.neutral_x)),
        neutral_y=float(d.get("neutral_y", AppConfig.neutral_y)),
        neutral_z=float(d.get("neutral_z", AppConfig.neutral_z)),
        travel_speed=float(d.get("travel_speed", AppConfig.travel_speed)),
        move_z_velocity=float(
            d.get(
                "move_z_velocity",
                d.get("z_speed", AppConfig.move_z_velocity),
            )
        ),
        camera_width=int(d.get("camera_width", AppConfig.camera_width)),
        camera_height=int(d.get("camera_height", AppConfig.camera_height)),
        detection_confidence_threshold=float(
            d.get(
                "detection_confidence_threshold",
                AppConfig.detection_confidence_threshold,
            )
        ),
        tracking_kp=float(d.get("tracking_kp", AppConfig.tracking_kp)),
        tracking_ki=float(d.get("tracking_ki", AppConfig.tracking_ki)),
        tracking_integral_max_px=int(
            d.get("tracking_integral_max_px", AppConfig.tracking_integral_max_px)
        ),
        tracking_deadzone_px=int(
            d.get("tracking_deadzone_px", AppConfig.tracking_deadzone_px)
        ),
        tracking_min_step_mm=float(
            d.get("tracking_min_step_mm", AppConfig.tracking_min_step_mm)
        ),
        tracking_max_step_mm=float(
            d.get("tracking_max_step_mm", AppConfig.tracking_max_step_mm)
        ),
        tracking_target_lost_frames=int(
            d.get("tracking_target_lost_frames", AppConfig.tracking_target_lost_frames)
        ),
        search_step_mm=float(d.get("search_step_mm", AppConfig.search_step_mm)),
        vision_staleness_s=float(
            d.get("vision_staleness_s", AppConfig.vision_staleness_s)
        ),
        system_network=_system_network_from_dict(d.get("system_network")),
        detection=_detection_from_dict(d.get("detection")),
        vision_classes_include=_int_id_list(d.get("vision_classes_include")),
        vision_classes_exclude=_int_id_list(d.get("vision_classes_exclude")),
        vision_class_thresholds=_class_thresholds_from_dict(
            d.get("vision_class_thresholds")
        ),
    )


def load_config(path: str | Path | None = None) -> AppConfig:
    global _CONFIG

    cfg_path = Path(path) if path is not None else _default_config_path()

    if not cfg_path.exists():
        default_cfg = AppConfig()
        _save_config_to_file(default_cfg, cfg_path)
        _CONFIG = default_cfg
        return default_cfg

    with cfg_path.open("r", encoding="utf-8") as f:
        data: Dict[str, Any] = json.load(f)

    _CONFIG = _config_from_dict(data)
    return _CONFIG


def _save_config_to_file(cfg: AppConfig, path: Path) -> None:
    payload = {
        "jetson_ip": cfg.jetson_ip,
        "api_port": cfg.api_port,
        "camera_port": cfg.camera_port,
        "moonraker_host": cfg.moonraker_host,
        "moonraker_port": cfg.moonraker_port,
        "moonraker_path": cfg.moonraker_path,
        "esp32_ip": cfg.esp32_ip,
        "laptop_ip": cfg.laptop_ip,
        "x_min": cfg.x_min,
        "x_max": cfg.x_max,
        "y_min": cfg.y_min,
        "y_max": cfg.y_max,
        "z_min": cfg.z_min,
        "z_max": cfg.z_max,
        "neutral_x": cfg.neutral_x,
        "neutral_y": cfg.neutral_y,
        "neutral_z": cfg.neutral_z,
        "travel_speed": cfg.travel_speed,
        "move_z_velocity": cfg.move_z_velocity,
        "camera_width": cfg.camera_width,
        "camera_height": cfg.camera_height,
        "detection_confidence_threshold": cfg.detection_confidence_threshold,
        "tracking_kp": cfg.tracking_kp,
        "tracking_ki": cfg.tracking_ki,
        "tracking_integral_max_px": cfg.tracking_integral_max_px,
        "tracking_deadzone_px": cfg.tracking_deadzone_px,
        "tracking_min_step_mm": cfg.tracking_min_step_mm,
        "tracking_max_step_mm": cfg.tracking_max_step_mm,
        "tracking_target_lost_frames": cfg.tracking_target_lost_frames,
        "search_step_mm": cfg.search_step_mm,
        "vision_staleness_s": cfg.vision_staleness_s,
        "system_network": copy.deepcopy(cfg.system_network),
        "detection": copy.deepcopy(cfg.detection),
        "vision_classes_include": list(cfg.vision_classes_include),
        "vision_classes_exclude": list(cfg.vision_classes_exclude),
        "vision_class_thresholds": copy.deepcopy(cfg.vision_class_thresholds),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


def get_config() -> AppConfig:
    global _CONFIG
    if _CONFIG is None:
        _CONFIG = load_config()
    return _CONFIG


def save_config(cfg: AppConfig | None = None, path: str | Path | None = None) -> None:
    target = cfg or get_config()
    cfg_path = Path(path) if path is not None else _default_config_path()
    _save_config_to_file(target, cfg_path)


def apply_network_response_to_config(cfg: AppConfig, data: Dict[str, Any]) -> None:
    """Merge GET /config/network JSON into cfg (only keys that are present)."""
    if not isinstance(data, dict):
        return
    if "moonraker_host" in data and data["moonraker_host"] is not None:
        cfg.moonraker_host = str(data["moonraker_host"])
    if "moonraker_port" in data and data["moonraker_port"] is not None:
        cfg.moonraker_port = int(data["moonraker_port"])
    if "moonraker_path" in data and data["moonraker_path"] is not None:
        cfg.moonraker_path = str(data["moonraker_path"])
    if "esp32_ip" in data and data["esp32_ip"] is not None:
        cfg.esp32_ip = str(data["esp32_ip"])
    for key in ("laptop_ip", "client_ip"):
        if key in data and data[key] is not None and str(data[key]).strip():
            cfg.laptop_ip = str(data[key]).strip()
            break
    if "stream_port" in data and data["stream_port"] is not None:
        cfg.camera_port = int(data["stream_port"])


def _motion_source_dict(data: Dict[str, Any]) -> Dict[str, Any]:
    """Prefer \"current\", then \"updated\", then flat body from motion responses."""
    cur = data.get("current")
    if isinstance(cur, dict):
        return cur
    upd = data.get("updated")
    if isinstance(upd, dict):
        return upd
    return data


def apply_motion_response_to_config(cfg: AppConfig, data: Dict[str, Any]) -> None:
    """Merge GET /config/motion (or {current, updated}) into cfg."""
    if not isinstance(data, dict):
        return
    data = _motion_source_dict(data)
    float_keys = (
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
        "detection_confidence_threshold",
        "tracking_kp",
        "tracking_ki",
        "tracking_min_step_mm",
        "tracking_max_step_mm",
        "search_step_mm",
        "vision_staleness_s",
    )
    int_keys = (
        "camera_width",
        "camera_height",
        "tracking_deadzone_px",
        "tracking_integral_max_px",
        "tracking_target_lost_frames",
    )
    for key in float_keys:
        if key in data and data[key] is not None:
            setattr(cfg, key, float(data[key]))
    for key in int_keys:
        if key in data and data[key] is not None:
            setattr(cfg, key, int(data[key]))


def apply_detection_response_to_config(cfg: AppConfig, data: Dict[str, Any]) -> None:
    """
    Merge GET /config/detection (or a nested \"detection\" object) into cfg.detection.
    """
    if not isinstance(data, dict):
        return
    if "detection" in data and isinstance(data["detection"], dict):
        cfg.detection = {**cfg.detection, **copy.deepcopy(data["detection"])}
    else:
        cfg.detection = {**cfg.detection, **copy.deepcopy(data)}


def apply_system_network_response_to_config(cfg: AppConfig, data: Dict[str, Any]) -> None:
    """Store GET /system/network JSON for display (optional stream/control hints)."""
    if not isinstance(data, dict):
        return
    cfg.system_network = copy.deepcopy(data)


def apply_vision_classes_response_to_config(cfg: AppConfig, data: Dict[str, Any]) -> None:
    """Merge GET /config/vision/classes into cfg (include, exclude, class_thresholds)."""
    if not isinstance(data, dict):
        return
    if "include" in data and isinstance(data["include"], list):
        cfg.vision_classes_include = _int_id_list(data["include"])
    if "exclude" in data and isinstance(data["exclude"], list):
        cfg.vision_classes_exclude = _int_id_list(data["exclude"])
    thr = data.get("class_thresholds")
    if thr is None:
        thr = data.get("thresholds")
    if isinstance(thr, dict):
        cfg.vision_class_thresholds = _class_thresholds_from_dict(thr)


__all__ = [
    "AppConfig",
    "load_config",
    "get_config",
    "save_config",
    "apply_network_response_to_config",
    "apply_motion_response_to_config",
    "apply_detection_response_to_config",
    "apply_system_network_response_to_config",
    "apply_vision_classes_response_to_config",
]
