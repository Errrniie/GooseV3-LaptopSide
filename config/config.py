from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
from typing import Any, Dict


@dataclass
class AppConfig:
    """
    Local snapshot of Jetson connection, network, and motion settings.
    Synced from GET /config/network and GET /config/motion via the GUI.
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

    # Motion (from GET /config/motion)
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
    z_speed: float = 5.0
    send_rate_hz: float = 10.0
    feedrate_multiplier: float = 2.0


_CONFIG: AppConfig | None = None


def _default_config_path() -> Path:
    return Path(__file__).with_name("config.json")


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
        z_speed=float(d.get("z_speed", AppConfig.z_speed)),
        send_rate_hz=float(d.get("send_rate_hz", AppConfig.send_rate_hz)),
        feedrate_multiplier=float(
            d.get("feedrate_multiplier", AppConfig.feedrate_multiplier)
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
        "z_speed": cfg.z_speed,
        "send_rate_hz": cfg.send_rate_hz,
        "feedrate_multiplier": cfg.feedrate_multiplier,
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


def apply_motion_response_to_config(cfg: AppConfig, data: Dict[str, Any]) -> None:
    """Merge GET /config/motion JSON into cfg (only keys that are present)."""
    if not isinstance(data, dict):
        return
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
        "z_speed",
        "send_rate_hz",
        "feedrate_multiplier",
    )
    for key in float_keys:
        if key in data and data[key] is not None:
            setattr(cfg, key, float(data[key]))


__all__ = [
    "AppConfig",
    "load_config",
    "get_config",
    "save_config",
    "apply_network_response_to_config",
    "apply_motion_response_to_config",
]
