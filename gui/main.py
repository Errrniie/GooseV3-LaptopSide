import json
import tkinter as tk

import requests
from tkinter import ttk, messagebox
from config import (
    apply_detection_response_to_config,
    apply_motion_response_to_config,
    apply_network_response_to_config,
    apply_system_network_response_to_config,
    apply_vision_classes_response_to_config,
    get_config,
    save_config,
)
from modes import get_system_modes, set_system_mode
from network.print_ipv4 import get_ipv4
from gui.clickable_video import open_clickable_video_window
from gui.tk_gst_video import TkGstVideoWidget
from jetson_client import (
    start_tracking,
    stop_tracking,
    move_z,
    laser_on,
    laser_off,
    laser_status,
    emergency_stop,
    firmware_restart,
    klipper_restart,
    tmc_dump,
    post_handshake,
    jetson_ip_from_handshake_response,
    get_network_config,
    get_motion_config,
    get_detection_config,
    get_system_network,
    get_vision_classes_config,
    get_vision_detection,
    push_local_config_to_jetson,
)


def fetch_and_apply_remote_config(*, quiet: bool = False) -> bool:
    """
    GET /config/network, /config/motion, and /config/detection (if present),
    merge into local AppConfig, save JSON. Prints responses to the terminal.
    """
    try:
        net = get_network_config()
        mot = get_motion_config()
        cfg = get_config()
        apply_network_response_to_config(cfg, net)
        apply_motion_response_to_config(cfg, mot)
        print("GET /config/network:\n" + json.dumps(net, indent=2, sort_keys=True))
        print("GET /config/motion:\n" + json.dumps(mot, indent=2, sort_keys=True))
        try:
            det = get_detection_config()
            apply_detection_response_to_config(cfg, det)
            print(
                "GET /config/detection:\n"
                + json.dumps(det, indent=2, sort_keys=True)
            )
        except requests.HTTPError as exc:
            resp = getattr(exc, "response", None)
            if resp is not None and resp.status_code == 404:
                print(
                    "GET /config/detection: 404 (endpoint not deployed) — "
                    "detection block left unchanged."
                )
            else:
                raise
        try:
            sn = get_system_network()
            apply_system_network_response_to_config(cfg, sn)
            print(
                "GET /system/network:\n"
                + json.dumps(sn, indent=2, sort_keys=True)
            )
        except requests.HTTPError as exc:
            resp = getattr(exc, "response", None)
            if resp is not None and resp.status_code == 404:
                print(
                    "GET /system/network: 404 — system network snapshot left unchanged."
                )
            else:
                raise
        try:
            vc = get_vision_classes_config()
            apply_vision_classes_response_to_config(cfg, vc)
            print(
                "GET /config/vision/classes:\n"
                + json.dumps(vc, indent=2, sort_keys=True)
            )
        except requests.HTTPError as exc:
            resp = getattr(exc, "response", None)
            if resp is not None and resp.status_code == 404:
                print(
                    "GET /config/vision/classes: 404 (endpoint not deployed) — "
                    "vision class lists left unchanged."
                )
            else:
                raise
        save_config(cfg)
        if not quiet:
            messagebox.showinfo(
                "Config",
                "Fetched network, motion, detection, and vision/classes (if available) "
                "from the API and saved to config.json.",
            )
        return True
    except Exception as exc:  # noqa: BLE001
        err = f"Failed to fetch config from API: {exc}"
        print(err)
        messagebox.showerror("Jetson Error", err)
        return False


def on_vision_detection_fetch() -> None:
    """GET /vision/detection — bbox overlay data for the laptop UI."""
    try:
        data = get_vision_detection()
        text = json.dumps(data, indent=2, sort_keys=True)
        print(f"GET /vision/detection:\n{text}")
        snippet = text if len(text) < 2500 else text[:2500] + "\n…"
        messagebox.showinfo("GET /vision/detection", snippet)
    except requests.RequestException as exc:
        err = f"Vision detection failed: {exc}"
        print(err)
        messagebox.showerror("Jetson Error", err)
    except Exception as exc:  # noqa: BLE001
        err = f"Vision detection failed: {exc}"
        print(err)
        messagebox.showerror("Jetson Error", err)


def on_start_tracking() -> None:
    try:
        resp = start_tracking()
        msg = f"Start tracking: {resp.status_code}"
        print(msg)
        messagebox.showinfo("Jetson", msg)
    except Exception as exc:  # noqa: BLE001 – simple GUI handler
        err = f"Failed to start tracking: {exc}"
        print(err)
        messagebox.showerror("Jetson Error", err)


def on_stop_tracking() -> None:
    try:
        resp = stop_tracking()
        msg = f"Stop tracking: {resp.status_code}"
        print(msg)
        messagebox.showinfo("Jetson", msg)
    except Exception as exc:  # noqa: BLE001 – simple GUI handler
        err = f"Failed to stop tracking: {exc}"
        print(err)
        messagebox.showerror("Jetson Error", err)


def on_move_z_plus_one() -> None:
    try:
        v = float(get_config().move_z_velocity)
        resp = move_z(1.0, velocity=v)
        msg = f"Move Z +1mm (V={v}): {resp.status_code}"
        print(msg)
        messagebox.showinfo("Jetson", msg)
    except Exception as exc:  # noqa: BLE001
        err = f"Failed to move Z: {exc}"
        print(err)
        messagebox.showerror("Jetson Error", err)


def on_move_z_minus_one() -> None:
    try:
        v = float(get_config().move_z_velocity)
        resp = move_z(-1.0, velocity=v)
        msg = f"Move Z -1mm (V={v}): {resp.status_code}"
        print(msg)
        messagebox.showinfo("Jetson", msg)
    except Exception as exc:  # noqa: BLE001
        err = f"Failed to move Z: {exc}"
        print(err)
        messagebox.showerror("Jetson Error", err)


def _laser_response_preview(resp: requests.Response, max_len: int = 800) -> str:
    try:
        data = resp.json()
        text = json.dumps(data, indent=2, sort_keys=True)
    except ValueError:
        text = (resp.text or "").strip()
    if len(text) > max_len:
        return text[:max_len] + "\n…(truncated)"
    return text or "(empty body)"


def on_laser_on() -> None:
    try:
        resp = laser_on()
        resp.raise_for_status()
        preview = _laser_response_preview(resp)
        print(f"POST /laser/on HTTP {resp.status_code}\n{preview}")
        messagebox.showinfo("Laser", f"ON — HTTP {resp.status_code}\n\n{preview}")
    except requests.RequestException as exc:
        err = f"Laser ON failed: {exc}"
        if getattr(exc, "response", None) is not None:
            err += f"\n\n{_laser_response_preview(exc.response)}"
        print(err)
        messagebox.showerror("Laser", err)
    except Exception as exc:  # noqa: BLE001
        err = f"Laser ON failed: {exc}"
        print(err)
        messagebox.showerror("Laser", err)


def on_laser_off() -> None:
    try:
        resp = laser_off()
        resp.raise_for_status()
        preview = _laser_response_preview(resp)
        print(f"POST /laser/off HTTP {resp.status_code}\n{preview}")
        messagebox.showinfo("Laser", f"OFF — HTTP {resp.status_code}\n\n{preview}")
    except requests.RequestException as exc:
        err = f"Laser OFF failed: {exc}"
        if getattr(exc, "response", None) is not None:
            err += f"\n\n{_laser_response_preview(exc.response)}"
        print(err)
        messagebox.showerror("Laser", err)
    except Exception as exc:  # noqa: BLE001
        err = f"Laser OFF failed: {exc}"
        print(err)
        messagebox.showerror("Laser", err)


def on_laser_status() -> None:
    try:
        resp = laser_status()
        resp.raise_for_status()
        preview = _laser_response_preview(resp)
        print(f"GET /laser/status HTTP {resp.status_code}\n{preview}")
        messagebox.showinfo("Laser status", f"HTTP {resp.status_code}\n\n{preview}")
    except requests.RequestException as exc:
        err = f"Laser status failed: {exc}"
        if getattr(exc, "response", None) is not None:
            err += f"\n\n{_laser_response_preview(exc.response)}"
        print(err)
        messagebox.showerror("Laser", err)
    except Exception as exc:  # noqa: BLE001
        err = f"Laser status failed: {exc}"
        print(err)
        messagebox.showerror("Laser", err)


def on_emergency_stop() -> None:
    if not messagebox.askyesno(
        "Confirm Emergency Stop",
        "This will send an EMERGENCY STOP (M112) to Klipper.\nAre you sure?",
    ):
        return
    try:
        resp = emergency_stop()
        msg = f"Emergency Stop (M112): {resp.status_code}"
        print(msg, resp.text)
        messagebox.showinfo("Jetson", msg)
    except Exception as exc:  # noqa: BLE001
        err = f"Failed to send emergency stop: {exc}"
        print(err)
        messagebox.showerror("Jetson Error", err)


def on_firmware_restart() -> None:
    try:
        resp = firmware_restart()
        msg = f"Firmware Restart: {resp.status_code}"
        print(msg, resp.text)
        messagebox.showinfo(
            "Jetson",
            msg + "\nKlipper will take a few seconds to come back.",
        )
    except Exception as exc:  # noqa: BLE001
        err = f"Failed to send firmware restart: {exc}"
        print(err)
        messagebox.showerror("Jetson Error", err)


def on_klipper_restart() -> None:
    try:
        resp = klipper_restart()
        msg = f"Klipper Restart: {resp.status_code}"
        print(msg, resp.text)
        messagebox.showinfo(
            "Jetson",
            msg + "\nKlipper will take a few seconds to restart.",
        )
    except Exception as exc:  # noqa: BLE001
        err = f"Failed to send Klipper restart: {exc}"
        print(err)
        messagebox.showerror("Jetson Error", err)


def _show_tmc_result(stepper: str, resp_text: str, status: int) -> None:
    # Show a short snippet of the response if it's long
    snippet = resp_text.strip()
    if len(snippet) > 600:
        snippet = snippet[:600] + "\n...\n(truncated)"
    messagebox.showinfo(
        "TMC Diagnostics",
        f"TMC dump for {stepper} (status {status}):\n\n{snippet}",
    )


def on_tmc_z() -> None:
    try:
        resp = tmc_dump("stepper_z")
        _show_tmc_result("stepper_z", resp.text, resp.status_code)
    except Exception as exc:  # noqa: BLE001
        err = f"Failed to request TMC dump for Z: {exc}"
        print(err)
        messagebox.showerror("Jetson Error", err)


def on_tmc_x() -> None:
    try:
        resp = tmc_dump("stepper_x")
        _show_tmc_result("stepper_x", resp.text, resp.status_code)
    except Exception as exc:  # noqa: BLE001
        err = f"Failed to request TMC dump for X: {exc}"
        print(err)
        messagebox.showerror("Jetson Error", err)


def on_tmc_y() -> None:
    try:
        resp = tmc_dump("stepper_y")
        _show_tmc_result("stepper_y", resp.text, resp.status_code)
    except Exception as exc:  # noqa: BLE001
        err = f"Failed to request TMC dump for Y: {exc}"
        print(err)
        messagebox.showerror("Jetson Error", err)


def on_handshake() -> None:
    try:
        client_ip = get_ipv4()
        print(f"Handshake: sending client_ip={client_ip!r}")
        resp = post_handshake(client_ip)
        resp.raise_for_status()
        jetson_ip = jetson_ip_from_handshake_response(resp)
        cfg = get_config()
        if jetson_ip:
            cfg.jetson_ip = jetson_ip
            save_config(cfg)
            print(f"Handshake OK. Saved Jetson IP: {jetson_ip}")
            messagebox.showinfo(
                "Handshake",
                f"OK (HTTP {resp.status_code})\nSaved Jetson IP: {jetson_ip}",
            )
        else:
            print(
                "Handshake OK (HTTP "
                f"{resp.status_code}). No jetson_ip in JSON response; "
                f"config unchanged. Current Jetson IP: {cfg.jetson_ip!r}"
            )
            messagebox.showinfo(
                "Handshake",
                f"OK (HTTP {resp.status_code})\n"
                "Response had no Jetson IP field — config not updated.\n"
                f"Current Jetson IP in config: {cfg.jetson_ip}",
            )
    except OSError as exc:
        err = f"Could not get this machine's IPv4: {exc}"
        print(err)
        messagebox.showerror("Handshake", err)
    except Exception as exc:  # noqa: BLE001
        err = f"Handshake failed: {exc}"
        print(err)
        messagebox.showerror("Jetson Error", err)


def on_open_video(root: tk.Tk) -> None:
    """Open video in a Tk window: TCP JPEG stream + PIL + bbox overlay."""
    cfg = get_config()
    video_port = cfg.camera_port

    win = tk.Toplevel(root)
    win.title(f"Video — TCP {cfg.jetson_ip}:{video_port}")
    win.transient(root)
    win.minsize(640, 400)
    win.geometry("960x600")

    outer = ttk.Frame(win, padding=8)
    outer.pack(fill=tk.BOTH, expand=True)

    status = ttk.Label(
        outer, text=f"Connecting to {cfg.jetson_ip}:{video_port} (TCP JPEG)…"
    )
    status.pack(anchor="w", pady=(0, 8))

    video_box = ttk.Frame(outer)
    video_box.pack(fill=tk.BOTH, expand=True)

    player = TkGstVideoWidget(video_box, video_port, draw_bbox=True)
    player.label.pack(fill=tk.BOTH, expand=True)

    def on_close() -> None:
        player.stop()
        win.destroy()

    win.protocol("WM_DELETE_WINDOW", on_close)

    ok, err = player.start()
    if not ok:
        messagebox.showerror(
            "Video Error",
            f"Could not start video stream.\n\n{err}\n\n"
            "Install: opencv-python-headless (or opencv-python), numpy, Pillow.\n"
            "Arch: sudo pacman -S python-opencv python-numpy python-pillow",
        )
        win.destroy()
        return

    print(f"Video stream started: TCP {cfg.jetson_ip}:{video_port}.")
    status.config(
        text=f"Streaming TCP {cfg.jetson_ip}:{video_port}. Close this window to stop."
    )


def open_config_window(parent: tk.Tk) -> None:
    cfg = get_config()

    win = tk.Toplevel(parent)
    win.title("Configuration")
    win.transient(parent)
    win.grab_set()
    win.minsize(460, 420)

    outer = ttk.Frame(win, padding=12)
    outer.grid(row=0, column=0, sticky="nsew")
    win.rowconfigure(0, weight=1)
    win.columnconfigure(0, weight=1)
    outer.rowconfigure(0, weight=1)
    outer.columnconfigure(0, weight=1)

    nb = ttk.Notebook(outer)
    nb.grid(row=0, column=0, sticky="nsew")

    entries: dict[str, ttk.Entry] = {}

    def add_row(parent: ttk.Frame, label: str, key: str, value: str, row: int) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=2, padx=(0, 8))
        entry = ttk.Entry(parent, width=28)
        entry.insert(0, value)
        entry.grid(row=row, column=1, sticky="ew", pady=2)
        entries[key] = entry

    def tab_with_scroll(parent_title: str) -> ttk.Frame:
        tab = ttk.Frame(nb, padding=8)
        nb.add(tab, text=parent_title)
        tab.columnconfigure(1, weight=1)
        return tab

    conn = tab_with_scroll("Connection")
    ttk.Label(
        conn,
        text=(
            "Jetson IP and API port are only used on this laptop to reach the HTTP API "
            "(not sent in POST /config)."
        ),
        wraplength=420,
    ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))
    add_row(conn, "Jetson IP", "jetson_ip", cfg.jetson_ip, 1)
    add_row(conn, "API Port", "api_port", str(cfg.api_port), 2)
    add_row(conn, "Camera / stream port (UDP)", "camera_port", str(cfg.camera_port), 3)

    net = tab_with_scroll("Network")
    ttk.Label(
        net,
        text=(
            "GET/POST /config/network — partial POST (only changed fields). "
            "Saved to config.json; Save pushes Moonraker, ESP32, laptop IP, path, "
            "and stream port from Camera/stream on Connection tab."
        ),
        wraplength=420,
    ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))
    add_row(net, "Moonraker host", "moonraker_host", cfg.moonraker_host, 1)
    add_row(net, "Moonraker port", "moonraker_port", str(cfg.moonraker_port), 2)
    add_row(net, "Moonraker path", "moonraker_path", cfg.moonraker_path, 3)
    add_row(net, "ESP32 IP", "esp32_ip", cfg.esp32_ip, 4)
    add_row(net, "Laptop IP (POST + GET)", "laptop_ip", cfg.laptop_ip, 5)

    mot = tab_with_scroll("Motion")
    ttk.Label(
        mot,
        text=(
            "POST /config/motion (partial update). travel_speed = travel feed; "
            "move_z_velocity = MOVE_Z macro V. Response includes updated/current — "
            "we merge from current on Get from API."
        ),
        wraplength=420,
    ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))
    motion_axes_fields: list[tuple[str, str, str]] = [
        ("x_min", "X min", "float"),
        ("x_max", "X max", "float"),
        ("y_min", "Y min", "float"),
        ("y_max", "Y max", "float"),
        ("z_min", "Z min", "float"),
        ("z_max", "Z max", "float"),
        ("neutral_x", "Neutral X", "float"),
        ("neutral_y", "Neutral Y", "float"),
        ("neutral_z", "Neutral Z", "float"),
        ("travel_speed", "Travel speed (feed)", "float"),
        ("move_z_velocity", "Move Z velocity (macro V)", "float"),
    ]
    for i, (key, label, _k) in enumerate(motion_axes_fields):
        add_row(mot, label, key, str(getattr(cfg, key)), i + 1)

    vis = tab_with_scroll("Vision / tracking")
    ttk.Label(
        vis,
        text=(
            "Same POST /config/motion — camera, detection threshold, PI tracking (Ki=0 → P-only), "
            "integral clamp, deadzone, steps, target-lost, search (partial update)."
        ),
        wraplength=420,
    ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))
    motion_vision_fields: list[tuple[str, str, str]] = [
        ("camera_width", "Camera width (px)", "int"),
        ("camera_height", "Camera height (px)", "int"),
        ("detection_confidence_threshold", "Detection confidence threshold", "float"),
        ("tracking_kp", "Tracking Kp", "float"),
        ("tracking_ki", "Tracking Ki (integral gain)", "float"),
        ("tracking_integral_max_px", "Tracking integral max (px clamp)", "int"),
        ("tracking_deadzone_px", "Tracking deadzone (px)", "int"),
        ("tracking_min_step_mm", "Tracking min step (mm)", "float"),
        ("tracking_max_step_mm", "Tracking max step (mm)", "float"),
        ("tracking_target_lost_frames", "Target lost (frames)", "int"),
        ("search_step_mm", "Search step (mm)", "float"),
        ("vision_staleness_s", "Vision staleness (s)", "float"),
    ]
    for i, (key, label, _k) in enumerate(motion_vision_fields):
        add_row(vis, label, key, str(getattr(cfg, key)), i + 1)

    vis_cls = tab_with_scroll("Vision classes")
    ttk.Label(
        vis_cls,
        text=(
            "GET/POST /config/vision/classes — YOLO class whitelist (include/exclude IDs) "
            "and optional per-class confidence floors as a JSON object "
            '(e.g. {"person": 0.45, "bird": 0.3}). Save pushes with the other config routes.'
        ),
        wraplength=420,
    ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))
    ttk.Label(vis_cls, text="Include class IDs (comma-separated)", font=("", 9)).grid(
        row=1, column=0, sticky="w", pady=(4, 0)
    )
    vis_include_entry = ttk.Entry(vis_cls, width=48)
    vis_include_entry.insert(
        0, ", ".join(str(x) for x in cfg.vision_classes_include)
    )
    vis_include_entry.grid(row=1, column=1, sticky="ew", pady=(4, 0))
    ttk.Label(vis_cls, text="Exclude class IDs (comma-separated)", font=("", 9)).grid(
        row=2, column=0, sticky="w", pady=(2, 0)
    )
    vis_exclude_entry = ttk.Entry(vis_cls, width=48)
    vis_exclude_entry.insert(
        0, ", ".join(str(x) for x in cfg.vision_classes_exclude)
    )
    vis_exclude_entry.grid(row=2, column=1, sticky="ew", pady=(2, 0))
    ttk.Label(vis_cls, text="Per-class thresholds (JSON object)", font=("", 9)).grid(
        row=3, column=0, sticky="nw", pady=(6, 0)
    )
    vis_thr_frame = ttk.Frame(vis_cls)
    vis_thr_frame.grid(row=3, column=1, sticky="nsew", pady=(6, 0))
    vis_thr_frame.rowconfigure(0, weight=1)
    vis_thr_frame.columnconfigure(0, weight=1)
    vis_thr_scroll = ttk.Scrollbar(vis_thr_frame, orient=tk.VERTICAL)
    vis_thr_text = tk.Text(
        vis_thr_frame,
        height=5,
        width=40,
        font=("Courier New", 10),
        yscrollcommand=vis_thr_scroll.set,
        wrap=tk.NONE,
    )
    vis_thr_scroll.config(command=vis_thr_text.yview)
    vis_thr_text.insert("1.0", json.dumps(cfg.vision_class_thresholds, indent=2))
    vis_thr_text.grid(row=0, column=0, sticky="nsew")
    vis_thr_scroll.grid(row=0, column=1, sticky="ns")
    vis_cls.rowconfigure(3, weight=1)
    vis_cls.columnconfigure(1, weight=1)

    sys_tab = tab_with_scroll("System network")
    ttk.Label(
        sys_tab,
        text=(
            "GET /system/network (Jetson IP, peer, stream port, control_api_port). "
            "Refreshed on Get from API; stored in config.json (local only, not POSTed)."
        ),
        wraplength=420,
    ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 6))
    sys_text_frame = ttk.Frame(sys_tab)
    sys_text_frame.grid(row=1, column=0, columnspan=2, sticky="nsew", pady=(0, 4))
    sys_text_frame.rowconfigure(0, weight=1)
    sys_text_frame.columnconfigure(0, weight=1)
    sys_scroll = ttk.Scrollbar(sys_text_frame, orient=tk.VERTICAL)
    sys_text = tk.Text(
        sys_text_frame,
        height=10,
        width=50,
        font=("Courier New", 10),
        yscrollcommand=sys_scroll.set,
        wrap=tk.NONE,
    )
    sys_scroll.config(command=sys_text.yview)
    sys_text.insert("1.0", json.dumps(cfg.system_network, indent=2))
    sys_text.grid(row=0, column=0, sticky="nsew")
    sys_scroll.grid(row=0, column=1, sticky="ns")
    sys_tab.rowconfigure(1, weight=1)
    sys_tab.columnconfigure(0, weight=1)

    det = tab_with_scroll("Detection")
    ttk.Label(
        det,
        text=(
            "GET/POST /config/detection — body is the JSON object below. "
            "Get from API refreshes it; Save pushes to Jetson. "
            "Use get_config().detection in code."
        ),
        wraplength=400,
    ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 6))
    det_text_frame = ttk.Frame(det)
    det_text_frame.grid(row=1, column=0, columnspan=2, sticky="nsew", pady=(0, 4))
    det_text_frame.rowconfigure(0, weight=1)
    det_text_frame.columnconfigure(0, weight=1)
    det_scroll = ttk.Scrollbar(det_text_frame, orient=tk.VERTICAL)
    det_text = tk.Text(
        det_text_frame,
        height=14,
        width=50,
        font=("Courier New", 10),
        yscrollcommand=det_scroll.set,
        wrap=tk.NONE,
    )
    det_scroll.config(command=det_text.yview)
    det_text.insert("1.0", json.dumps(cfg.detection, indent=2))
    det_text.grid(row=0, column=0, sticky="nsew")
    det_scroll.grid(row=0, column=1, sticky="ns")
    det.rowconfigure(1, weight=1)
    det.columnconfigure(0, weight=1)

    def fill_from_cfg() -> None:
        c = get_config()
        for key, w in entries.items():
            w.delete(0, tk.END)
            w.insert(0, str(getattr(c, key)))
        det_text.delete("1.0", tk.END)
        det_text.insert("1.0", json.dumps(c.detection, indent=2))
        sys_text.delete("1.0", tk.END)
        sys_text.insert("1.0", json.dumps(c.system_network, indent=2))
        vis_include_entry.delete(0, tk.END)
        vis_include_entry.insert(
            0, ", ".join(str(x) for x in c.vision_classes_include)
        )
        vis_exclude_entry.delete(0, tk.END)
        vis_exclude_entry.insert(
            0, ", ".join(str(x) for x in c.vision_classes_exclude)
        )
        vis_thr_text.delete("1.0", tk.END)
        vis_thr_text.insert("1.0", json.dumps(c.vision_class_thresholds, indent=2))

    def on_get_from_api() -> None:
        if fetch_and_apply_remote_config(quiet=True):
            fill_from_cfg()
            messagebox.showinfo(
                "Config",
                "Fetched config from the API (network, motion, detection, vision/classes, "
                "system/network) and saved to config.json.",
            )

    def _csv_int_ids(s: str) -> list[int]:
        out: list[int] = []
        for part in s.replace(",", " ").split():
            part = part.strip()
            if not part:
                continue
            out.append(int(part))
        return out

    def on_save() -> None:
        try:
            c = get_config()
            c.jetson_ip = entries["jetson_ip"].get().strip()
            c.api_port = int(entries["api_port"].get().strip())
            c.camera_port = int(entries["camera_port"].get().strip())
            c.moonraker_host = entries["moonraker_host"].get().strip()
            c.moonraker_port = int(entries["moonraker_port"].get().strip())
            c.moonraker_path = entries["moonraker_path"].get().strip()
            c.esp32_ip = entries["esp32_ip"].get().strip()
            c.laptop_ip = entries["laptop_ip"].get().strip()
            for key, _label, kind in motion_axes_fields + motion_vision_fields:
                raw = entries[key].get().strip()
                if kind == "int":
                    setattr(c, key, int(raw))
                else:
                    setattr(c, key, float(raw))
            raw_sys = sys_text.get("1.0", "end-1c").strip()
            if raw_sys:
                c.system_network = json.loads(raw_sys)
            else:
                c.system_network = {}
            raw_det = det_text.get("1.0", "end-1c").strip()
            if raw_det:
                c.detection = json.loads(raw_det)
            else:
                c.detection = {}
            c.vision_classes_include = _csv_int_ids(vis_include_entry.get())
            c.vision_classes_exclude = _csv_int_ids(vis_exclude_entry.get())
            raw_thr = vis_thr_text.get("1.0", "end-1c").strip()
            if raw_thr:
                thr = json.loads(raw_thr)
                if not isinstance(thr, dict):
                    raise ValueError(
                        "vision_thresholds: per-class thresholds must be a JSON object"
                    )
                try:
                    c.vision_class_thresholds = {
                        str(k): float(v) for k, v in thr.items()
                    }
                except (TypeError, ValueError) as thr_exc:
                    raise ValueError(
                        "vision_thresholds: each value must be a number"
                    ) from thr_exc
            else:
                c.vision_class_thresholds = {}
            save_config(c)
            net_resp, mot_resp, det_resp, vis_resp = push_local_config_to_jetson(c)
            net_resp.raise_for_status()
            mot_resp.raise_for_status()
            det_note = ""
            if det_resp.status_code == 404:
                det_note = (
                    "\n\nPOST /config/detection returned 404 — detection was saved locally only "
                    "(deploy that route on the Jetson to sync detection)."
                )
                print("POST /config/detection: 404 (not deployed)")
            else:
                det_resp.raise_for_status()
            vis_note = ""
            if vis_resp.status_code == 404:
                vis_note = (
                    "\n\nPOST /config/vision/classes returned 404 — vision class policy was "
                    "saved locally only (deploy that route on the Jetson to sync)."
                )
                print("POST /config/vision/classes: 404 (not deployed)")
            else:
                vis_resp.raise_for_status()
            print(f"POST /config/network HTTP {net_resp.status_code}")
            try:
                print(json.dumps(net_resp.json(), indent=2, sort_keys=True))
            except ValueError:
                print(net_resp.text)
            print(f"POST /config/motion HTTP {mot_resp.status_code}")
            try:
                print(json.dumps(mot_resp.json(), indent=2, sort_keys=True))
            except ValueError:
                print(mot_resp.text)
            print(f"POST /config/detection HTTP {det_resp.status_code}")
            try:
                print(json.dumps(det_resp.json(), indent=2, sort_keys=True))
            except ValueError:
                print(det_resp.text)
            print(f"POST /config/vision/classes HTTP {vis_resp.status_code}")
            try:
                print(json.dumps(vis_resp.json(), indent=2, sort_keys=True))
            except ValueError:
                print(vis_resp.text)
            messagebox.showinfo(
                "Config",
                "Saved to config.json and pushed to Jetson "
                "(POST /config/network, /config/motion, /config/detection, "
                "/config/vision/classes)."
                + det_note
                + vis_note,
            )
            win.destroy()
        except json.JSONDecodeError as exc:
            messagebox.showerror(
                "Config Error",
                f"Detection, System network, or Vision class thresholds: invalid JSON.\n{exc}",
            )
        except ValueError as exc:
            if str(exc).startswith("vision_thresholds:"):
                messagebox.showerror("Config Error", str(exc).split(":", 1)[1].strip())
            else:
                messagebox.showerror("Config Error", f"Invalid number: {exc}")
        except requests.RequestException as exc:
            err = f"Saved locally, but pushing to the API failed:\n{exc}"
            if getattr(exc, "response", None) is not None:
                err += f"\n\n{exc.response.text}"
            print(err)
            messagebox.showerror("Config / API", err)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Config Error", f"Failed to save config: {exc}")

    button_row = ttk.Frame(outer)
    button_row.grid(row=1, column=0, sticky="e", pady=(12, 0))

    ttk.Button(button_row, text="Cancel", command=win.destroy).grid(row=0, column=0, padx=(0, 8))
    ttk.Button(button_row, text="Get from API", command=on_get_from_api).grid(
        row=0, column=1, padx=(0, 8)
    )
    ttk.Button(button_row, text="Save", command=on_save).grid(row=0, column=2)


def create_main_window() -> None:
    root = tk.Tk()
    root.title("Simple Window")

    # Allow the window to be freely resized
    root.rowconfigure(0, weight=1)
    root.columnconfigure(0, weight=1)

    main_frame = ttk.Frame(root, padding=16)
    main_frame.grid(row=0, column=0, sticky="nsew")

    # Let the frame grow with the window
    main_frame.rowconfigure(0, weight=1)
    main_frame.rowconfigure(1, weight=0)
    main_frame.columnconfigure(0, weight=1)

    # Simple label area (can be replaced later with connection status, logs, etc.)
    info_label = ttk.Label(
        main_frame,
        text="This is a simple, resizable window.\nYou can add more controls here later.",
        anchor="center",
        justify="center",
    )
    info_label.grid(row=0, column=0, sticky="nsew", pady=(0, 12))

    modes_frame = ttk.LabelFrame(main_frame, text="System mode", padding=8)
    modes_frame.grid(row=1, column=0, sticky="ew", pady=(0, 12))
    modes_frame.columnconfigure(0, weight=1)

    mode_var = tk.StringVar()
    mode_combo = ttk.Combobox(modes_frame, textvariable=mode_var, width=28)
    mode_combo.grid(row=0, column=0, sticky="ew", padx=(0, 8))

    def on_refresh_modes() -> None:
        try:
            names = get_system_modes()
            mode_combo["values"] = tuple(names)
            if names:
                if not mode_var.get().strip() or mode_var.get() not in names:
                    mode_var.set(names[0])
            print(f"System modes: {names}")
            messagebox.showinfo(
                "System modes",
                f"Loaded {len(names)} mode(s). Choose one in the dropdown, then Set mode.",
            )
        except Exception as exc:  # noqa: BLE001
            err = f"Failed to fetch modes: {exc}"
            print(err)
            messagebox.showerror("Jetson Error", err)

    def on_set_mode() -> None:
        name = mode_var.get().strip()
        if not name:
            messagebox.showwarning("System mode", "Select or enter a mode name, then click Set mode.")
            return
        try:
            resp = set_system_mode(name)
            msg = f"Set mode to {name!r}: HTTP {resp.status_code}"
            print(msg, getattr(resp, "text", ""))
            messagebox.showinfo("System mode", msg)
        except Exception as exc:  # noqa: BLE001
            err = f"Failed to set mode: {exc}"
            print(err)
            messagebox.showerror("Jetson Error", err)

    ttk.Button(modes_frame, text="Refresh modes", command=on_refresh_modes).grid(
        row=0, column=1, padx=(0, 4)
    )
    ttk.Button(modes_frame, text="Set mode", command=on_set_mode).grid(row=0, column=2)

    handshake_frame = ttk.LabelFrame(main_frame, text="Handshake", padding=8)
    handshake_frame.grid(row=2, column=0, sticky="ew", pady=(0, 12))
    ttk.Label(
        handshake_frame,
        text="POST /system/handshake with this laptop's IPv4 as client_ip.",
    ).grid(row=0, column=0, sticky="w", padx=(0, 12))
    ttk.Button(handshake_frame, text="Send client IP", command=on_handshake).grid(
        row=0, column=1
    )

    api_cfg_frame = ttk.LabelFrame(main_frame, text="Config from API", padding=8)
    api_cfg_frame.grid(row=3, column=0, sticky="ew", pady=(0, 12))
    api_cfg_frame.columnconfigure(0, weight=1)
    ttk.Label(
        api_cfg_frame,
        text="GET config + /system/network (+ /config/detection if deployed) — updates config.json.",
    ).grid(row=0, column=0, sticky="w", padx=(0, 12))
    ttk.Button(
        api_cfg_frame,
        text="Get config from API",
        command=lambda: fetch_and_apply_remote_config(quiet=False),
    ).grid(row=0, column=1)

    # Tracking / Z row, then laser row (GET status + POST on/off per Jetson API)
    button_frame = ttk.Frame(main_frame)
    button_frame.grid(row=4, column=0, sticky="ew")
    for col in range(4):
        button_frame.columnconfigure(col, weight=1)

    btn_start = ttk.Button(
        button_frame,
        text="Start Tracking",
        command=on_start_tracking,
    )
    btn_start.grid(row=0, column=0, sticky="ew", padx=(0, 4))

    btn_stop = ttk.Button(
        button_frame,
        text="Stop Tracking",
        command=on_stop_tracking,
    )
    btn_stop.grid(row=0, column=1, sticky="ew", padx=(0, 4))

    btn_z_up = ttk.Button(
        button_frame,
        text="Z +1mm",
        command=on_move_z_plus_one,
    )
    btn_z_up.grid(row=0, column=2, sticky="ew", padx=(0, 4))

    btn_z_down = ttk.Button(
        button_frame,
        text="Z -1mm",
        command=on_move_z_minus_one,
    )
    btn_z_down.grid(row=0, column=3, sticky="ew", padx=(0, 4))

    laser_row = ttk.LabelFrame(button_frame, text="Laser (ESP32)", padding=(4, 4))
    laser_row.grid(row=1, column=0, columnspan=4, sticky="ew", pady=(8, 0))
    laser_row.columnconfigure(0, weight=1)
    laser_row.columnconfigure(1, weight=1)
    laser_row.columnconfigure(2, weight=1)

    ttk.Button(laser_row, text="Laser ON", command=on_laser_on).grid(
        row=0, column=0, sticky="ew", padx=(0, 4)
    )
    ttk.Button(laser_row, text="Laser OFF", command=on_laser_off).grid(
        row=0, column=1, sticky="ew", padx=(0, 4)
    )
    ttk.Button(laser_row, text="Laser status", command=on_laser_status).grid(
        row=0, column=2, sticky="ew"
    )

    # Second row for utility buttons
    util_frame = ttk.Frame(main_frame)
    util_frame.grid(row=5, column=0, sticky="ew", pady=(8, 0))
    for col in range(6):
        util_frame.columnconfigure(col, weight=1)

    btn_video = ttk.Button(
        util_frame,
        text="Open Video",
        command=lambda: on_open_video(root),
    )
    btn_video.grid(row=0, column=0, sticky="ew", padx=(0, 4))

    btn_clickable_video = ttk.Button(
        util_frame,
        text="Clickable Video",
        command=lambda: open_clickable_video_window(root),
    )
    btn_clickable_video.grid(row=0, column=1, sticky="ew", padx=(0, 4))

    btn_config = ttk.Button(
        util_frame,
        text="Config...",
        command=lambda: open_config_window(root),
    )
    btn_config.grid(row=0, column=2, sticky="ew", padx=(0, 4))

    btn_estop = ttk.Button(
        util_frame,
        text="EMERGENCY STOP",
        command=on_emergency_stop,
    )
    btn_estop.grid(row=0, column=3, sticky="ew", padx=(0, 4))

    btn_fw_restart = ttk.Button(
        util_frame,
        text="FW Restart",
        command=on_firmware_restart,
    )
    btn_fw_restart.grid(row=0, column=4, sticky="ew", padx=(0, 4))

    btn_klipper_restart = ttk.Button(
        util_frame,
        text="Klipper Restart",
        command=on_klipper_restart,
    )
    btn_klipper_restart.grid(row=0, column=5, sticky="ew")

    ttk.Button(
        util_frame,
        text="Vision bbox",
        command=on_vision_detection_fetch,
    ).grid(row=1, column=0, sticky="ew", padx=(0, 4), pady=(6, 0))

    # Third row for TMC diagnostics
    tmc_frame = ttk.Frame(main_frame)
    tmc_frame.grid(row=6, column=0, sticky="ew", pady=(8, 0))
    for col in range(3):
        tmc_frame.columnconfigure(col, weight=1)

    ttk.Button(
        tmc_frame,
        text="TMC Z",
        command=on_tmc_z,
    ).grid(row=0, column=0, sticky="ew", padx=(0, 4))

    ttk.Button(
        tmc_frame,
        text="TMC X",
        command=on_tmc_x,
    ).grid(row=0, column=1, sticky="ew", padx=(0, 4))

    ttk.Button(
        tmc_frame,
        text="TMC Y",
        command=on_tmc_y,
    ).grid(row=0, column=2, sticky="ew")

    # Start the Tk event loop
    root.mainloop()


if __name__ == "__main__":
    create_main_window()

