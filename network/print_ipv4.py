"""
Resolve this host's IPv4 on a wired Ethernet interface (not Wi‑Fi).

Used by the GUI to send POST /system/handshake with {\"client_ip\": \"...\"}.

Uses `ip -4 addr show` (iproute2). Picks the first IPv4 on a wired-looking interface.
"""
from __future__ import annotations

import re
import subprocess


def _is_wired_interface(name: str) -> bool:
    if not name or name == "lo":
        return False
    lower = name.lower()
    if lower.startswith(
        (
            "wlan",
            "wl",
            "docker",
            "br-",
            "virbr",
            "veth",
            "tailscale",
            "tun",
            "tap",
            "lo",
        )
    ):
        return False
    if lower.startswith(("eth", "enp", "eno", "ens", "enx", "usb")):
        return True
    return lower.startswith("en") and not lower.startswith(("wlan", "wl"))


def _ethernet_ipv4_pairs() -> list[tuple[str, str]]:
    try:
        proc = subprocess.run(
            ["ip", "-4", "addr", "show"],
            capture_output=True,
            text=True,
            check=True,
        )
    except FileNotFoundError as exc:
        raise OSError("'ip' not found; install iproute2 (iproute2 package).") from exc
    except subprocess.CalledProcessError as exc:
        raise OSError(exc.stderr or str(exc)) from exc

    out = proc.stdout
    current: str | None = None
    pairs: list[tuple[str, str]] = []

    for line in out.splitlines():
        m = re.match(r"^\d+:\s+(\S+):", line)
        if m:
            current = m.group(1)
            continue
        if current and "inet " in line and _is_wired_interface(current):
            m2 = re.search(r"inet\s+([\d.]+)/", line)
            if m2:
                pairs.append((current, m2.group(1)))

    return pairs


def get_ipv4() -> str:
    """Return IPv4 on the first wired Ethernet interface that has one."""
    pairs = _ethernet_ipv4_pairs()
    if not pairs:
        raise OSError(
            "No IPv4 on a wired Ethernet interface (plug in cable or check interface)."
        )
    return pairs[0][1]


def main() -> None:
    import sys

    try:
        print(get_ipv4())
    except OSError as exc:
        print(exc, file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
