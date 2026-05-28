# GooseV3-Laptop — Comprehensive Project Reference

> **Audience:** AI coding agents (and engineers) who need a complete mental model of this codebase before making any change. Read this end-to-end before editing. Everything in this document is derived from the actual source as of the current commit; defaults shown match `config/config.py` and the on-disk `config/config.json`.

---

## 1. What this project is

**GooseV3-Laptop** is the **laptop-side client** of a two-machine robotic deterrent system. It is a Python 3 Tkinter desktop application that:

1. **Talks to a Jetson device** over HTTP. The Jetson hosts a FastAPI-style control plane on port `8000`, performs YOLO-based computer vision, runs object tracking, and bridges to a Klipper/Moonraker motion stack on `:7125` plus an ESP32 (laser controller).
2. **Receives a live MJPEG-equivalent video stream** (length-prefixed JPEGs over TCP) on port `5000`, decodes it with OpenCV, overlays detection/tracking bounding boxes, and renders it in a `pygame` window.
3. **Lets a human operator command the rig**: start/stop tracking, jog the Z axis, fire/disarm the laser, click-to-aim, edit and push configuration, restart firmware, request TMC stepper diagnostics, send an emergency stop.

The companion repository (not in this directory) is the Jetson server (`GooseV3-Jetson` or similar) that exposes the HTTP endpoints this client calls.

### High-level dataflow

```
+---------------------------+              +----------------------------+
|        LAPTOP             |   HTTP :8000 |          JETSON            |
|                           | <----------> |  FastAPI control API       |
|  Tkinter GUI (gui/)       |              |  YOLO vision + tracker     |
|  jetson_client.py         |  TCP  :5000  |  TCP JPEG frame server     |
|  config/AppConfig         | <----------- |  -> length-prefixed JPEGs  |
|  pygame renderer          |              |                            |
|                           |              |  HTTP :7125 -> Moonraker   |
|                           |              |  (Klipper) -> stepper X/Y/Z|
|                           |              |  HTTP/UDP  -> ESP32 laser  |
+---------------------------+              +----------------------------+
```

### Tech stack

- **Language:** Python 3 (uses `from __future__ import annotations`).
- **GUI:** Tkinter / `ttk` (standard library).
- **Video rendering:** `pygame` window blitted from OpenCV-decoded NumPy frames.
- **Image decode:** `opencv-python-headless` (or full `opencv-python`).
- **HTTP:** `requests`.
- **Numerics:** `numpy`.
- **Optional UI imaging:** `Pillow` (in `requirements.txt`, not actively imported in the current source — kept as a fallback).
- **Persistence:** A single JSON file at `config/config.json`.

### Required environment

- `pip install -r requirements.txt` installs: `requests>=2.31`, `Pillow>=10`, `numpy>=1.26`, `opencv-python-headless>=4.8`, `pygame>=2.5`.
- **`ip` command (iproute2)** is required at runtime for the handshake (see `network/print_ipv4.py`). This means the laptop is expected to be Linux-flavored (or anything with `ip -4 addr show`). macOS does not ship `iproute2` and will need it installed or this function adapted.
- Network reachability to the Jetson on its `jetson_ip` for ports `8000` (control API) and `5000` (TCP JPEG stream). Moonraker `7125` and ESP32 `8266`-style endpoints are reached **by the Jetson**, not the laptop.

---

## 2. Directory layout

```
GooseV3-Laptop/
├── main.py                     # Entry point; calls gui.main.create_main_window()
├── jetson_client.py            # HTTP client + CLI for the Jetson control API
├── requirements.txt            # Python deps
├── README.md                   # Minimal user-facing README
├── config/
│   ├── __init__.py             # Re-exports AppConfig + load/save/apply helpers
│   ├── config.py               # AppConfig dataclass, JSON load/save, merge helpers
│   └── config.json             # Persisted local config (auto-created on first load)
├── gui/
│   ├── main.py                 # Tkinter app: create_main_window() + Config dialog
│   ├── clickable_video.py      # Video window with click-to-coordinates capture
│   ├── tk_gst_video.py         # TCP JPEG receiver + pygame renderer + bbox overlay
│   └── vision_bbox.py          # Parses /vision/detection JSON into overlay rectangles
├── modes/
│   ├── __init__.py             # Re-exports get_system_modes, set_system_mode
│   └── api.py                  # GET /system/modes, POST /system/mode
├── network/
│   └── print_ipv4.py           # Find this host's wired Ethernet IPv4 (for handshake)
└── MD_Folder/
    └── PROJECT_OVERVIEW.md     # (this file)
```

There is no test suite, no packaging metadata, no linter config. The project is a single-process desktop app.

---

## 3. Entry point and bootstrap

### [main.py](../main.py)

Trivial bootstrap:

```python
from gui.main import create_main_window
def main() -> None:
    create_main_window()
if __name__ == "__main__":
    main()
```

Run with `python main.py` from the repo root. Working directory matters because `config/config.json` is resolved relative to `config/config.py` (`Path(__file__).with_name("config.json")`).

`gui/main.py` also has its own `if __name__ == "__main__"` block that does the same thing — running `python gui/main.py` would work but is not the documented way (and would require the parent dir to be on `sys.path`).

---

## 4. Configuration system (`config/`)

### [config/config.py](../config/config.py) — `AppConfig` dataclass

`AppConfig` is the **single source of truth on the laptop** for everything the Jetson exposes. Fields:

#### Core Jetson connection (laptop → Jetson HTTP)
| Field | Default | Purpose |
|---|---|---|
| `jetson_ip` | `192.168.0.100` | Base host for all HTTP calls |
| `api_port` | `8000` | Control API port |
| `camera_port` | `5000` | TCP JPEG stream port (also mirrored as `stream_port` in the network config blob) |

#### Network (Moonraker, ESP32, laptop)
| Field | Default | Purpose |
|---|---|---|
| `moonraker_host` | `192.168.8.146` | Moonraker (Klipper API) host the Jetson should talk to |
| `moonraker_port` | `7125` | Moonraker port |
| `moonraker_path` | `""` | Optional path prefix |
| `esp32_ip` | `192.168.8.186` | Laser ESP32 IP |
| `laptop_ip` | `""` | Laptop's IP — sent in the handshake / network POST |

#### Motion limits and neutrals (Klipper coordinate space, units = mm)
`x_min/x_max=0.0/11.5`, `y_min/y_max=0.0/7.6`, `z_min/z_max=0.0/7.0`, `neutral_x=5.75`, `neutral_y=3.8`, `neutral_z=3.0`. These are travel envelope guards and the "home / rest" pose used by the Jetson when no target is active.

#### Speeds
- `travel_speed=4000.0` — Klipper feedrate for general travel moves (server units, typically mm/min).
- `move_z_velocity=2.5` — `V` parameter for the `MOVE_Z` macro (mm/s on the server). Used by `move_z()`.

#### Camera + vision
- `camera_width=1920`, `camera_height=1080` — native frame size assumption used by the vision pipeline.
- `detection_confidence_threshold=0.6` — global YOLO confidence floor.

#### PI tracking gains (servo loop on the Jetson)
- `tracking_kp=0.003`, `tracking_ki=0.0` (Ki=0 ⇒ P-only).
- `tracking_integral_max_px=400` — anti-windup clamp.
- `tracking_deadzone_px=30` — px error below which no command is issued.
- `tracking_min_step_mm=0.05`, `tracking_max_step_mm=3.0` — per-iteration mm step range.
- `tracking_target_lost_frames=5` — frames with no detection before the tracker drops the target.
- `search_step_mm=1.0` — step size of the search scan when no target is visible.
- `vision_staleness_s=0.5` — max age (seconds) of a detection frame before it is treated as stale.

#### Mirrors of Jetson-owned blobs
- `system_network` — last `GET /system/network` snapshot (read-only on laptop side; never POSTed).
- `detection` — arbitrary JSON for `/config/detection` (model selection, NMS, etc.).
- `vision_classes_include` / `_exclude` — YOLO class ID allow/deny lists.
- `vision_class_thresholds` — `{"person": 0.45, ...}` per-class confidence overrides.

### Persistence

`config.json` lives next to `config.py`. `load_config()` is lazy — `_CONFIG` is a module-level singleton populated by the first `get_config()` call. **Mutating `get_config()` mutates the singleton in place; `save_config(cfg)` writes it back.** There is no locking — the GUI is single-threaded for config edits.

If the file does not exist, `load_config()` writes a fresh `AppConfig()` to disk and returns it.

### Backwards-compat tolerances in `_config_from_dict`

- `move_z_velocity` will fall back to a legacy `z_speed` field if present.
- All numeric coercions are wrapped in `float(...)` / `int(...)` so JSON with stringy numbers still loads.

### Merge helpers (`apply_*_response_to_config`)

The GUI uses these to fold server responses back into `AppConfig` without trampling fields the server did not return:

- `apply_network_response_to_config` — accepts `moonraker_host/port/path`, `esp32_ip`, `laptop_ip` **or** `client_ip` (first non-empty wins), `stream_port` (maps to `cfg.camera_port`).
- `apply_motion_response_to_config` — handles three response shapes:
  - flat `{key: value}`
  - `{"current": {...}}` — preferred when present (most server endpoints return both `current` and `updated` after a POST)
  - `{"updated": {...}}` — fallback
- `apply_detection_response_to_config` — merges either the top-level dict or the nested `detection` field into `cfg.detection` (dict merge, not replace).
- `apply_system_network_response_to_config` — overwrites `cfg.system_network` wholesale (display-only).
- `apply_vision_classes_response_to_config` — overwrites `include`, `exclude`, and `class_thresholds` (accepts `class_thresholds` or legacy `thresholds`).

### [config/__init__.py](../config/__init__.py)

Just re-exports the public surface above for `from config import ...`.

### [config/config.json](../config/config.json) — current on-disk state

This file holds the **live operator settings** and is overwritten by `save_config()`. The committed copy shows the lab IPs (`192.168.8.x`), `travel_speed=1000.0`, and `tracking_ki=0.001` — i.e., it has diverged from the dataclass defaults already. Treat it as state, not as documentation.

---

## 5. Jetson HTTP client (`jetson_client.py`)

This is the single boundary module between the laptop and the Jetson API. **All HTTP calls to the Jetson go through here** (with the small exception of `modes/api.py` which mirrors the same pattern for the modes endpoints).

`_base_url()` reads the singleton config: `f"http://{cfg.jetson_ip}:{cfg.api_port}"`. So changing the Jetson IP in the GUI changes the target of every subsequent call without restart — there is no module-level URL cache.

### Endpoints, in calling order through the UI

#### Handshake / discovery
- **`POST /system/handshake`** → `post_handshake(client_ip)` with `{"client_ip": "<ipv4>"}`. The Jetson may return its own IP under one of `jetson_ip / server_ip / device_ip / host_ip / jetson` — `jetson_ip_from_handshake_response(resp)` checks each in that order and returns the first non-empty value, which the GUI then persists to `cfg.jetson_ip`.

#### Tracking
- **`POST /start_tracking`** → `start_tracking()`.
- **`POST /stop_tracking`** → `stop_tracking()`.

#### Manual aim / motion
- **`POST /move_laser`** with `{"x": float, "y": float}` → `move_laser(x, y)`. Defined but **not currently bound to any GUI button** — kept for programmatic / future use.
- **`POST /z/move`** with `{"delta_mm": float, "velocity": float}` → `move_z(delta_mm, velocity=2.0)`. Conceptually issues a Klipper `MOVE_Z D=... V=...` macro. The velocity is conditionally added so the server's default applies when caller leaves it `None`.

#### Laser (ESP32 bridge)
- **`GET /laser/status`** → `laser_status()`.
- **`POST /laser/on`** → `laser_on()`.
- **`POST /laser/off`** → `laser_off()`.

#### Config — network
- **`GET /config/network`** → `get_network_config()` returns the parsed JSON dict directly (raises on non-2xx).
- **`POST /config/network`** → `update_network_config(...)`. Partial update: only `not-None` arguments are included in the body.

#### Config — motion (also covers tracking & camera params)
- **`GET /config/motion`** → `get_motion_config()`.
- **`POST /config/motion`** → `update_motion_config(**kwargs)`. The allowed keys are gated by `_MOTION_POST_KEYS` (a `frozenset`); anything outside it is silently dropped. **If you add a new tunable to `AppConfig`, you must also add it to `_MOTION_POST_KEYS` for the push to include it.**

#### Config — detection (arbitrary blob)
- **`GET /config/detection`** → `get_detection_config()`.
- **`POST /config/detection`** → `update_detection_config(updates)`. Whole dict is sent; semantics (replace vs merge) are server-side.

#### Config — vision classes
- **`GET /config/vision/classes`** → `get_vision_classes_config()`.
- **`POST /config/vision/classes`** → `update_vision_classes_config(include, exclude, class_thresholds)`. Partial body (only non-None keys).

#### System inspection (read-only)
- **`GET /system/network`** → `get_system_network()` — reports Jetson IP, peer IP, stream port, control API port.
- **`GET /vision/detection`** → `get_vision_detection()` — the live overlay payload (see §7 for shape).

#### Safety / maintenance (raw Klipper hooks via the server)
- **`POST /emergency_stop`** → `emergency_stop()` — sends `M112`.
- **`POST /firmware_restart`** → `firmware_restart()`.
- **`POST /klipper_restart`** → `klipper_restart()`.
- **`POST /tmc/dump`** with `{"stepper": "stepper_z"}` → `tmc_dump(stepper)` — TMC stepper driver diagnostics.

#### Click-to-distance
- **`POST /click`** with `{"x": int, "y": int, "timestamp"?: float}` → `send_click(x, y, timestamp=None)`. Coordinates are sent in the **3840×2160** click space (see §8 for the mapping math).

### `push_local_config_to_jetson(cfg)`

Convenience aggregator used by the Config dialog's **Save** button and by the `python jetson_client.py push` CLI. It calls, in order:

1. `update_network_config` (with `moonraker_*`, `esp32_ip`, `laptop_ip` (None if empty), `stream_port = cfg.camera_port`)
2. `update_motion_config` (full set of motion/vision/tracking params)
3. `update_detection_config(cfg.detection)`
4. `update_vision_classes_config(include=..., exclude=..., class_thresholds=...)`

Returns the 4-tuple of `requests.Response` objects so the caller can inspect each status. The GUI **tolerates 404** on `/config/detection` and `/config/vision/classes` — it warns "endpoint not deployed" and keeps going. Network and motion 404s/errors do propagate.

### CLI mode

Running `python jetson_client.py` as a script gives a small admin tool:

- `python jetson_client.py get network|motion|detection|system-network|vision-detection|vision-classes` — prints pretty-printed JSON of the corresponding GET.
- `python jetson_client.py push` — runs `push_local_config_to_jetson(get_config())` and prints each response.

Errors bubble up via `SystemExit(1)`.

### `camera_stream_url()`

Returns `http://<JETSON_IP>:<camera_port>/video`. The video pipeline does **not** actually use HTTP — the live renderer connects with a raw TCP socket (see §7). This helper is reserved for a future browser fallback or debugging by hand.

---

## 6. Modes (`modes/api.py`)

Two endpoints, structured identically to `jetson_client.py`:

- **`GET /system/modes`** → `get_system_modes(timeout=5.0) -> list[str]`. Tolerates the response being either a bare list or a dict containing one under `modes / mode_names / names / valid_modes`. Raises `ValueError` if neither shape matches.
- **`POST /system/mode`** with `{"mode": "<name>"}` → `set_system_mode(mode)`.

Surfaced in the GUI's main window as the **System mode** combobox + "Refresh modes" + "Set mode" buttons.

---

## 7. Video pipeline (`gui/tk_gst_video.py` + `gui/vision_bbox.py`)

This is the most subtle subsystem. Despite its filename (`tk_gst_video.py` — there is **no GStreamer here, the name is historical**), the implementation is:

> **Raw TCP socket → length-prefixed JPEG frames → OpenCV decode → bounding-box draw → pygame window.**

### Wire format

Each frame on the wire:

```
[ 4 bytes: big-endian uint32 size (struct '>I') ][ JPEG bytes (length = size) ]
```

`_MAX_JPEG_BYTES = 50 * 1024 * 1024` (50 MB) is the upper guard before the connection is treated as desynced.

### Class: `TkGstVideoWidget`

Constructed by both `gui/main.py::on_open_video` and `gui/clickable_video.py::start_video_stream`. Key parameters:

- `parent: tk.Widget` — used only to spawn the placeholder `tk.Label` (the actual video does **not** live in Tk; see below).
- `video_port: int` — the TCP port to connect to.
- `jetson_ip: Optional[str]` — defaults to `get_config().jetson_ip` (lazy import to avoid a cycle).
- `draw_bbox: bool` — when True, also spawns a poller for `GET /vision/detection`.
- `poll_ms: int = 100` — bbox poll interval.
- `on_native_frame_size: Optional[Callable[[int,int], None]]` — invoked once per frame on the Tk main thread (via `master.after(0, ...)`) so the GUI can react to the discovered native resolution.

**Important Tk quirk:** `self.label = tk.Label(parent, ...)` exists for backwards compatibility — the legacy code path packed video into this label. The current implementation **renders into a separate pygame window** opened by `_pygame_loop()`. The label is still kept in the Tk widget tree because:
1. `event_xy_to_native(...)` uses `self.label.winfo_width()/winfo_height()` to relate Tk click coordinates to display pixels.
2. `clickable_video.py` binds `<Button-1>` to it.

The label simply shows the text `(Rendering in pygame window)` while video is active.

### Threading model

`start()` spins up **three daemon threads**:

1. **`tcp-video-stream`** (`_tcp_recv_loop`):
   - Outer reconnect loop with 0.5 s backoff.
   - Inner loop: `recv_exact(4)` → unpack length → `recv_exact(length)` → `cv2.imdecode(...)` → enqueue.
   - 2-second socket timeout per `recv`, `TCP_NODELAY` and `SO_KEEPALIVE` set best-effort.
   - Prints `[STREAM] Frames received: N, queue size: Q` every 30 frames.

2. **`vision-detection-poll`** (`_poll_bbox_loop`) — only if `draw_bbox=True`:
   - Loops `get_vision_detection(timeout=2.0)` every `poll_ms`.
   - Stores the latest dict under `self._bbox_data` guarded by `self._bbox_lock`.

3. **`pygame-render`** (`_pygame_loop`):
   - `pygame.init()` then `pygame.display.set_mode((1280, 720), pygame.RESIZABLE)`.
   - Pulls a frame from the queue (`get(timeout=1.0)`); on empty, prints `[RENDER] Queue empty - waiting for frame`.
   - Records `native_w/h` from each frame; reports back via `_on_native_frame_size` on the Tk thread.
   - If `draw_bbox`, calls `parse_overlay_boxes(self._bbox_data)` and draws scaled rectangles directly onto the BGR frame with `cv2.rectangle`.
   - Active track is drawn at thickness 4, inactive at 2.
   - Color is set per-box: `green` → BGR (0,255,0), `red` / `#ff0000` → (0,0,255), anything else → yellow (0,255,255).
   - `cv2.cvtColor(BGR→RGB)` → `pygame.surfarray.make_surface(rgb.swapaxes(0,1))` → `pygame.transform.scale` → blit → flip.
   - Captures `display_w/h` for later coordinate mapping.
   - On any render exception, recreates the pygame window in-place and continues.
   - **The pygame `QUIT` event flips `self._running = False`** — closing the pygame window stops the whole pipeline.
   - Clock capped at 60 fps.

**Queue policy:** `_frame_queue` has `maxsize=2`. If full, the receive thread drops the oldest frame (`_frame_queue.get_nowait()` then put). This is **important** — it prefers latency over completeness.

### `stop()`

Sets `_running=False`, shuts down the socket (best-effort `shutdown` + `close` under `_sock_lock`), joins the threads with bounded timeouts (2.0 s for stream/pygame, 1.0 s for poll), drains the frame queue, clears the label text.

### Coordinate mapping (`event_xy_to_native`)

Maps a click on `self.label` (Tk widget coordinates) into the canonical **3840×2160** click coordinate space the Jetson expects (`POST /click`). The chain is:

1. **Label → pygame display:** if label and display sizes differ, assume the displayed image is centered with `(lw-dw)/2`, `(lh-dh)/2` offsets; otherwise treat them as 1:1.
2. **Display → native frame** (using `native_w/h` learned from the actual decoded JPEGs).
3. **Native → 3840×2160 click space** (a pure ratio scale).

All steps clamp to valid ranges. If `native_w/h` are 0 (no frame yet), it falls back to display size.

> **Gotcha:** because the pygame window is independent of the Tk label, the in-Tk click currently maps **the label's bounding box**, which is *not* where the user actually sees the image. The `event_xy_to_native` math assumes the displayed image lives in the Tk label. In the current pygame-based rendering this means click-on-label is a stale UI from the previous (Tk-pack-PIL) era. **`clickable_video.py` still uses this code path**, so clicks register on the placeholder label, not on the pygame window. If you need true click-to-aim, either re-wire to handle pygame mouse events or restore Tk-based rendering. Treat this as a known limitation, not an invariant.

### `gui/vision_bbox.py` — overlay parser

`parse_overlay_boxes(data)` returns `(list_of_boxes, frame_width, frame_height)`. Each box is `(x, y, w, h, color_string, is_active_bool)` in **frame pixel space**.

It tries, in order:

1. **`tracks: [...]`** — preferred multi-track payload from the server. Each entry must have `bbox = [x1,y1,x2,y2]`. Active track is the one whose `object_id` matches the top-level `active_object_id`.
2. **`detections: [...]`** — multi-class detection list (no tracker IDs). If the server also sends `active_track: {bbox: ...}`, the entry whose bbox matches exactly is marked active.
3. **Legacy single bbox** — via `parse_bbox_and_frame(data)`, which itself handles:
   - `detection.bbox / detection.box`
   - top-level `bbox / box / rect`
   - explicit `x1,y1,x2,y2` fields
   - normalized coords (all `|v|<=1.0`) → multiplied by frame size
   - heuristic xyxy-vs-xywh disambiguation: treats as `xyxy` when `(x2,y2)` lie inside the frame and the implied width/height are non-negative; otherwise `xywh`.
   - dict-form `{x|left, y|top, w|width|x2|right, h|height|y2|bottom}` variants.

If `has_target: false` is set in the legacy payload, returns `None` early.

Frame size: prefers `frame_width/frame_height`, falls back to `camera_width/camera_height`, then `(1920, 1080)`.

**Color rules** (`outline_color_for_track`):
- `class_name == "person"` or `class_id == 0` → `#00cc00` (green).
- `class_name` contains `goose/geese` or `bird`, or `class_id == 14` → `red`.
- Otherwise → `#cccc00` (yellow).

This is what determines whether you see a green or red box in the live feed.

---

## 8. Tkinter GUI (`gui/main.py`)

`create_main_window()` builds a single resizable top-level window with the following sections, top to bottom:

### 8.1 Header label

A static `ttk.Label` reading `"This is a simple, resizable window. You can add more controls here later."` — placeholder for future status.

### 8.2 System mode (`row=1`)

- `ttk.Combobox` bound to `mode_var`.
- **Refresh modes**: calls `get_system_modes()`, populates the combobox values, auto-selects the first entry if none is set.
- **Set mode**: `set_system_mode(mode_var.get())` and shows the HTTP status.

### 8.3 Handshake (`row=2`)

- Single button "Send client IP". Resolves the wired Ethernet IPv4 with `network.print_ipv4.get_ipv4()` (raises `OSError` if no wired iface is found), posts to `/system/handshake`, and if the response contains a Jetson IP, persists it via `save_config(cfg)`.

### 8.4 Config from API (`row=3`)

- **Get config from API**: calls `fetch_and_apply_remote_config(quiet=False)`.

This helper is the **canonical "sync down"** path:

1. `get_network_config()` → `apply_network_response_to_config`.
2. `get_motion_config()` → `apply_motion_response_to_config`.
3. `get_detection_config()` (tolerates 404, leaves block unchanged).
4. `get_system_network()` (tolerates 404).
5. `get_vision_classes_config()` (tolerates 404).
6. `save_config(cfg)` to persist.
7. Pretty-prints each response to stdout; shows a single `messagebox.showinfo` summary unless `quiet=True`.

### 8.5 Tracking & Z row (`row=4`)

Four-column row: **Start Tracking**, **Stop Tracking**, **Z +1mm**, **Z -1mm**.

The Z buttons call `move_z(±1.0, velocity=cfg.move_z_velocity)`. Each handler shows status via `messagebox` and prints to stdout.

### 8.6 Laser row (under tracking, `row=1` inside `button_frame`)

- **Laser ON / Laser OFF / Laser status** — each calls the corresponding `laser_*()` function and renders a JSON-or-text preview (`_laser_response_preview`, capped at 800 chars).

### 8.7 Utilities row (`row=5`)

Six columns: **Open Video**, **Clickable Video**, **Config...**, **EMERGENCY STOP**, **FW Restart**, **Klipper Restart**.

- **Open Video** (`on_open_video(root)`): opens a `Toplevel` window with a `TkGstVideoWidget(video_box, video_port, draw_bbox=True)`. Pygame window opens on `player.start()`. Closing the Toplevel calls `player.stop()`.
- **Clickable Video**: see §9.
- **Config...**: see §8.9.
- **EMERGENCY STOP**: confirms via `messagebox.askyesno("Confirm Emergency Stop", ...)` before issuing `M112`.
- **FW Restart / Klipper Restart**: fire-and-forget POSTs with status display.

### 8.8 Sub-row inside utilities (`row=1`)

- **Vision bbox**: calls `get_vision_detection()` and dumps the JSON into a messagebox (truncated to 2500 chars).

### 8.9 TMC diagnostics row (`row=6`)

- **TMC Z / TMC X / TMC Y**: each posts to `/tmc/dump` with the corresponding stepper name and displays a snippet (capped at 600 chars).

### 8.10 Config dialog (`open_config_window(parent)`)

Modal `Toplevel` with a `ttk.Notebook` (six tabs). Each tab edits a subset of `AppConfig`:

| Tab | Fields |
|---|---|
| **Connection** | `jetson_ip`, `api_port`, `camera_port` (purely local — not POSTed in `/config/network` except `camera_port` which is sent as `stream_port`) |
| **Network** | `moonraker_host/port/path`, `esp32_ip`, `laptop_ip` |
| **Motion** | `x_min/max`, `y_min/max`, `z_min/max`, `neutral_x/y/z`, `travel_speed`, `move_z_velocity` (all stored as Python floats, formatted via `str(...)`) |
| **Vision / tracking** | `camera_width/height` (int), `detection_confidence_threshold`, `tracking_kp/ki`, `tracking_integral_max_px`, `tracking_deadzone_px`, `tracking_min_step_mm`, `tracking_max_step_mm`, `tracking_target_lost_frames`, `search_step_mm`, `vision_staleness_s` |
| **Vision classes** | Comma-separated `include` IDs, `exclude` IDs, and a `tk.Text` widget holding a JSON object for `class_thresholds` |
| **System network** | Read-only-ish JSON blob — editable but only persisted locally |
| **Detection** | `tk.Text` JSON editor for the `detection` blob |

Three buttons:

- **Cancel** — closes without saving.
- **Get from API** — `fetch_and_apply_remote_config(quiet=True)` then `fill_from_cfg()` repopulates every widget.
- **Save** — parses every entry into `AppConfig`, calls `save_config(c)`, then `push_local_config_to_jetson(c)`. Tolerates `/config/detection` and `/config/vision/classes` returning 404 (notes it in the success message). Catches `json.JSONDecodeError` (for the three JSON Text widgets), `ValueError` for numeric fields, and `requests.RequestException` separately so the user gets actionable error text.

The per-class thresholds parser asserts the JSON parses to a dict and that every value coerces to `float`, otherwise raises a `ValueError` with a `"vision_thresholds:"` prefix which the handler strips before showing.

---

## 9. Clickable video (`gui/clickable_video.py`)

Spawned from the **Clickable Video** button. Wraps a `TkGstVideoWidget(draw_bbox=True)` inside a `Toplevel` plus a coordinate-capture UI.

### UI

- Instructions label at the top.
- **Click Coordinates** group: X entry (0–3840), Y entry (0–2160), **Send Coordinates** button, **Auto-send on capture** checkbox.
- **Video Stream** group: live video area + **Start Video Stream** / **Stop Video Stream** buttons.

### Interaction

- `Start Video Stream` constructs a fresh `TkGstVideoWidget`, packs its placeholder label, binds `<Button-1>` to `on_video_click`, calls `player.start()`. On failure, surfaces the error string (suggests OpenCV/numpy/Pillow install commands).
- `on_video_click(event)` uses `player.event_xy_to_native(event.x, event.y)` to convert to 3840×2160 space, writes the result into the X/Y entries, optionally fires `send_coordinates(x, y)` if auto-send is on.
- `send_coordinates(x, y)` validates range (0–3840, 0–2160), `POST /click`, raises for status, parses JSON, and updates the status label.
- `Stop Video Stream` cleanly tears down the widget (calls `player.stop()`, destroys the label).
- Window close handler calls `stop_video_stream()` to avoid leaking the pygame window.

> See §7's "Gotcha" — clicks are bound to the Tk label, not the pygame window the user is actually looking at. The captured coordinates work mathematically for the label's bounding box, but for accurate click-to-aim you need to either bind directly to pygame's event loop or restore the Tk-image rendering path.

---

## 10. Wired IP discovery (`network/print_ipv4.py`)

Runs `ip -4 addr show` (iproute2). Pairs interfaces with their first IPv4 address; filters by `_is_wired_interface(name)`:

- **Excluded prefixes:** `wlan`, `wl`, `docker`, `br-`, `virbr`, `veth`, `tailscale`, `tun`, `tap`, `lo`.
- **Included prefixes:** `eth`, `enp`, `eno`, `ens`, `enx`, `usb`.
- Also includes `en*` not starting with `wlan/wl` (catches macOS-style `en0`, etc., though macOS lacks `ip` so this branch is effectively Linux-only with predictable network interface names).

Returns the first match. Raises `OSError` if none. CLI: `python network/print_ipv4.py` prints the IP (used for manual debugging).

This is the **handshake source**: `gui/main.py::on_handshake` calls `get_ipv4()` and posts it to `/system/handshake`.

---

## 11. End-to-end runtime flow

### First-time bring-up

1. Operator runs `python main.py`. `gui/main.py::create_main_window()` builds the UI.
2. `get_config()` lazily loads or creates `config/config.json`.
3. Operator clicks **Send client IP** (Handshake). The laptop sends its wired IPv4 to `/system/handshake`. If the Jetson echoes back `jetson_ip`, the laptop persists it.
4. Operator clicks **Get config from API**. The five sync GETs populate `AppConfig` and `config.json`.
5. Operator opens **Config...**, adjusts tunables, clicks **Save**, which writes `config.json` and POSTs `network`, `motion`, `detection`, `vision/classes` back.

### Live operation

1. Operator clicks **Open Video** (or **Clickable Video**).
2. `TkGstVideoWidget.start()` opens the TCP socket to `<jetson_ip>:5000`, spawns the receive thread, the bbox-poll thread, and the pygame render thread.
3. The pygame window appears showing the live stream with bounding boxes overlaid (green = person, red = goose/bird, yellow = other).
4. Operator clicks **Start Tracking** → Jetson begins servo'ing the rig at the active target.
5. Operator clicks **Laser ON** when ready, **Laser OFF** when done.
6. **EMERGENCY STOP** → `M112` to Klipper if anything goes wrong.

### Click-to-aim flow (Clickable Video)

1. Operator clicks on the video.
2. Click coordinates (Tk-label space) are converted via `event_xy_to_native` to 3840×2160 space.
3. Either automatically (auto-send checkbox) or via **Send Coordinates**, `POST /click` is issued.
4. The Jetson performs distance estimation / target selection and returns a JSON status.

### Shutdown

Closing the main window stops the Tk mainloop. Video players hold daemon threads — they exit with the process, but if you close the Toplevel first, `stop()` joins them cleanly.

---

## 12. Conventions and gotchas (read before editing)

- **`from __future__ import annotations`** is used everywhere except `gui/main.py` and `gui/clickable_video.py`. Match the surrounding file's convention.
- **Singleton config:** `get_config()` returns the same `AppConfig` instance every call. Treat it as mutable shared state. After mutating fields directly, call `save_config(cfg)` to persist.
- **Adding a new tunable** to `AppConfig`:
  1. Add to the dataclass with a sensible default.
  2. Add a load entry in `_config_from_dict`.
  3. Add a save entry in `_save_config_to_file`.
  4. **If the Jetson should learn about it,** add it to `_MOTION_POST_KEYS` (or whichever endpoint), add the kwarg to `update_motion_config(...)`'s call site in `push_local_config_to_jetson`, and update `apply_motion_response_to_config` to read it back.
  5. Add a row to the appropriate Notebook tab in `gui/main.py::open_config_window` and remember to also update `fill_from_cfg()` and `on_save()`.
- **HTTP error handling** is inconsistent on purpose: top-level "destructive" actions (start/stop, restarts, e-stop) print + `messagebox.showerror` but do not raise. Sync-down (`fetch_and_apply_remote_config`) tolerates 404 only on `detection`, `system/network`, and `vision/classes`; other 4xx/5xx propagate via `requests.HTTPError`. The aggregate **Save** in the Config dialog mirrors that 404-tolerance for the same two routes.
- **Threading:** all UI lives on the Tk main thread. Pygame rendering runs in its own thread (this is OK because the pygame window is independent and not a Tk child). HTTP polling lives in its own thread. **Never call `tkinter` widget methods from non-Tk threads** — `_on_native_frame_size` correctly marshals back via `master.after(0, ...)`.
- **Reconnect behavior:** the TCP receive loop reconnects forever (0.5 s sleep). There is no exponential backoff and no max-retries. If the Jetson is permanently down, the only visible signal is the `[STREAM]`/`[RENDER]` stdout messages stopping.
- **Frame queue is depth 2** and drops oldest on overflow — this is deliberate to keep latency low. Don't increase it unless you mean to.
- **`network/print_ipv4.py` assumes Linux with iproute2.** macOS users will need to either install iproute2-mac, adapt this to `ifconfig`, or skip the handshake.
- **`tk_gst_video.py`'s name is historical** — there is no GStreamer dependency. Don't `import gst*` anywhere expecting it.
- **`pygame.display.set_mode((1280, 720), pygame.RESIZABLE)`** is hard-coded. The window is resizable post-creation; resizing scales the blit with `pygame.transform.scale`.
- **`move_laser` HTTP function exists but is not wired to a button.** Adding a button for it is straightforward — call `move_laser(x_mm, y_mm)`.
- **`Pillow` is in `requirements.txt` but not currently imported.** It used to back a Tk-image render path; leaving it in `requirements.txt` is harmless and provides a fallback.
- **`opencv-python-headless` vs `opencv-python`**: either works. The headless variant is in `requirements.txt` for compatibility with servers; the GUI uses pygame, so the OpenCV GUI extras aren't needed.

---

## 13. Quick reference — every HTTP endpoint the laptop touches

| Method | Path | Helper | Used by |
|---|---|---|---|
| POST | `/system/handshake` | `post_handshake` | Handshake button |
| GET | `/system/modes` | `get_system_modes` | System mode "Refresh" |
| POST | `/system/mode` | `set_system_mode` | System mode "Set" |
| GET | `/system/network` | `get_system_network` | Config sync-down |
| POST | `/start_tracking` | `start_tracking` | "Start Tracking" |
| POST | `/stop_tracking` | `stop_tracking` | "Stop Tracking" |
| POST | `/move_laser` | `move_laser` | (defined, not wired) |
| POST | `/z/move` | `move_z` | "Z +1mm" / "Z -1mm" |
| GET | `/laser/status` | `laser_status` | "Laser status" |
| POST | `/laser/on` | `laser_on` | "Laser ON" |
| POST | `/laser/off` | `laser_off` | "Laser OFF" |
| GET | `/config/network` | `get_network_config` | Sync-down |
| POST | `/config/network` | `update_network_config` | Config Save |
| GET | `/config/motion` | `get_motion_config` | Sync-down |
| POST | `/config/motion` | `update_motion_config` | Config Save |
| GET | `/config/detection` | `get_detection_config` | Sync-down (tolerates 404) |
| POST | `/config/detection` | `update_detection_config` | Config Save (tolerates 404) |
| GET | `/config/vision/classes` | `get_vision_classes_config` | Sync-down (tolerates 404) |
| POST | `/config/vision/classes` | `update_vision_classes_config` | Config Save (tolerates 404) |
| GET | `/vision/detection` | `get_vision_detection` | Live bbox poller + "Vision bbox" button |
| POST | `/click` | `send_click` | Clickable video |
| POST | `/emergency_stop` | `emergency_stop` | "EMERGENCY STOP" |
| POST | `/firmware_restart` | `firmware_restart` | "FW Restart" |
| POST | `/klipper_restart` | `klipper_restart` | "Klipper Restart" |
| POST | `/tmc/dump` | `tmc_dump` | "TMC X/Y/Z" |
| TCP raw | `<jetson_ip>:5000` | `TkGstVideoWidget._tcp_recv_loop` | Video window |

---

## 14. Mental model summary (one paragraph)

The laptop is a thin, stateless-ish client. **All persistent state lives in `config/config.json`** — an in-memory `AppConfig` singleton mirrors it and is mutated by both the Config dialog and the `apply_*_response_to_config` merge helpers. **All communication with the Jetson** funnels through `jetson_client.py` (and `modes/api.py` for two modes endpoints). The GUI is a flat Tkinter window whose buttons each invoke one of those client functions, surface the response via `messagebox`, and print it to stdout. The video pipeline is independent: a TCP socket pulls length-prefixed JPEGs, OpenCV decodes them, a pygame window renders them, and a separate poll thread keeps a "latest bbox overlay" dict fresh so each rendered frame can be decorated. Click-to-aim translates Tk-label pixels to 3840×2160 click coordinates and POSTs them. Safety (emergency stop, firmware/klipper restart, TMC dumps) and click-to-aim are first-class operator actions — wire any new feature into one of the existing button rows in `gui/main.py::create_main_window` and a new helper in `jetson_client.py`.
