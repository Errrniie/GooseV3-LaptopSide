"""
Configuration package for GooseV3Laptop.

This is where we keep connection details and other settings, such as:
- Jetson IP / port
- API endpoints / topics
- Timeouts and other tunables
"""

from .config import (
    AppConfig,
    apply_detection_response_to_config,
    apply_motion_response_to_config,
    apply_network_response_to_config,
    apply_system_network_response_to_config,
    apply_vision_classes_response_to_config,
    get_config,
    load_config,
    save_config,
)

__all__ = [
    "AppConfig",
    "apply_detection_response_to_config",
    "apply_motion_response_to_config",
    "apply_network_response_to_config",
    "apply_system_network_response_to_config",
    "apply_vision_classes_response_to_config",
    "get_config",
    "load_config",
    "save_config",
]

