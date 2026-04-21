from __future__ import annotations

from typing import Any

import requests

from config import get_config


def _base_url() -> str:
    cfg = get_config()
    return f"http://{cfg.jetson_ip}:{cfg.api_port}"


def get_system_modes(timeout: float = 5.0) -> list[str]:
    """
    GET /system/modes — returns registered mode names from the Jetson API.
    Accepts a JSON list or an object with a list under 'modes', 'mode_names',
    'names', or 'valid_modes'.
    """
    url = f"{_base_url()}/system/modes"
    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()
    data: Any = resp.json()
    if isinstance(data, list):
        return [str(x) for x in data]
    if isinstance(data, dict):
        for key in ("modes", "mode_names", "names", "valid_modes"):
            if key in data and isinstance(data[key], list):
                return [str(x) for x in data[key]]
    raise ValueError(f"Unexpected /system/modes response: {data!r}")


def set_system_mode(mode: str, timeout: float = 5.0) -> requests.Response:
    """POST /system/mode with JSON {\"mode\": \"<string>\"}."""
    url = f"{_base_url()}/system/mode"
    return requests.post(url, json={"mode": mode}, timeout=timeout)
