import json
import tkinter as tk

import requests
from tkinter import ttk, messagebox
import subprocess
import threading
import time
import re

from config import (
    apply_motion_response_to_config,
    apply_network_response_to_config,
    get_config,
    save_config,
)
from modes import get_system_modes, set_system_mode
from network.print_ipv4 import get_ipv4
from jetson_client import (
    start_tracking,
    stop_tracking,
    move_z,
    laser_on,
    laser_off,
    emergency_stop,
    firmware_restart,
    klipper_restart,
    tmc_dump,
    send_click,
    post_handshake,
    jetson_ip_from_handshake_response,
    get_network_config,
    get_motion_config,
    push_local_config_to_jetson,
)


def fetch_and_apply_remote_config(*, quiet: bool = False) -> bool:
    """
    GET /config/network and /config/motion, merge into local AppConfig, save JSON.
    Prints both responses to the terminal. Optionally shows a success dialog.
    """
    try:
        net = get_network_config()
        mot = get_motion_config()
        cfg = get_config()
        apply_network_response_to_config(cfg, net)
        apply_motion_response_to_config(cfg, mot)
        save_config(cfg)
        print("GET /config/network:\n" + json.dumps(net, indent=2, sort_keys=True))
        print("GET /config/motion:\n" + json.dumps(mot, indent=2, sort_keys=True))
        if not quiet:
            messagebox.showinfo(
                "Config",
                "Fetched network and motion from the API and saved to config.json.",
            )
        return True
    except Exception as exc:  # noqa: BLE001
        err = f"Failed to fetch config from API: {exc}"
        print(err)
        messagebox.showerror("Jetson Error", err)
        return False


def _gstreamer_udp_play_cmd(video_port: int) -> str:
    """RTP/H264 UDP receiver pipeline for Jetson → laptop video."""
    return (
        f"gst-launch-1.0 udpsrc port={video_port} buffer-size=0 "
        'caps="application/x-rtp, media=video, encoding-name=H264, payload=96" '
        "! rtph264depay ! avdec_h264 max-threads=4 lowres=0 ! videoconvert ! "
        "autovideosink sync=false"
    )


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
        resp = move_z(1.0, velocity=2.0)
        msg = f"Move Z +1mm (V=2): {resp.status_code}"
        print(msg)
        messagebox.showinfo("Jetson", msg)
    except Exception as exc:  # noqa: BLE001
        err = f"Failed to move Z: {exc}"
        print(err)
        messagebox.showerror("Jetson Error", err)


def on_move_z_minus_one() -> None:
    try:
        resp = move_z(-1.0, velocity=2.0)
        msg = f"Move Z -1mm (V=2): {resp.status_code}"
        print(msg)
        messagebox.showinfo("Jetson", msg)
    except Exception as exc:  # noqa: BLE001
        err = f"Failed to move Z: {exc}"
        print(err)
        messagebox.showerror("Jetson Error", err)


def on_laser_on() -> None:
    try:
        resp = laser_on()
        msg = f"Laser ON: {resp.status_code}"
        print(msg)
        messagebox.showinfo("Jetson", msg)
    except Exception as exc:  # noqa: BLE001
        err = f"Failed to turn laser ON: {exc}"
        print(err)
        messagebox.showerror("Jetson Error", err)


def on_laser_off() -> None:
    try:
        resp = laser_off()
        msg = f"Laser OFF: {resp.status_code}"
        print(msg)
        messagebox.showinfo("Jetson", msg)
    except Exception as exc:  # noqa: BLE001
        err = f"Failed to turn laser OFF: {exc}"
        print(err)
        messagebox.showerror("Jetson Error", err)


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


def on_open_video() -> None:
    """
    Try to open the GStreamer video pipeline.
    If the process exits with an error within 5 seconds, show an error and stop.
    """
    cfg = get_config()
    video_port = cfg.camera_port  # Use the configured camera port (default 5000)

    cmd = _gstreamer_udp_play_cmd(video_port)

    # Check if gst-launch-1.0 exists first
    try:
        subprocess.run(
            ["which", "gst-launch-1.0"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=2.0,
        )
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        messagebox.showerror(
            "Video Error",
            "gst-launch-1.0 not found. Please install GStreamer:\n"
            "  Ubuntu/Debian: sudo apt install gstreamer1.0-tools gstreamer1.0-plugins-base gstreamer1.0-plugins-good gstreamer1.0-plugins-bad gstreamer1.0-libav",
        )
        return

    try:
        # Show a message that we're starting
        print(f"Starting video stream on UDP port {video_port}...")
        proc = subprocess.Popen(
            ["bash", "-lc", cmd],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        messagebox.showinfo(
            "Video Stream",
            f"Video stream started on port {video_port}.\n"
            "A video window should open shortly.\n"
            "If no video appears within 5 seconds, check the error message.",
        )
    except Exception as exc:  # noqa: BLE001
        messagebox.showerror("Video Error", f"Failed to start video pipeline: {exc}")
        return

    def monitor() -> None:
        time.sleep(5.0)
        ret = proc.poll()
        if ret is not None and ret != 0:
            # Process exited with error within 5 seconds
            stdout, stderr = proc.communicate()
            msg = stderr.decode("utf-8", errors="ignore") or stdout.decode(
                "utf-8", errors="ignore"
            )
            messagebox.showerror(
                "Video Error",
                f"Video stream did not start correctly within 5 seconds.\n"
                f"Listening on UDP port {video_port}.\n\n"
                f"Details:\n{msg.strip()}\n\n"
                f"Make sure the Jetson is streaming video to port {video_port}.",
            )

    threading.Thread(target=monitor, daemon=True).start()


def open_clickable_video_window(parent: tk.Tk) -> None:
    """
    Open a clickable video window for distance estimation.
    Launches GStreamer UDP video stream and provides coordinate input interface.
    """
    cfg = get_config()
    video_port = cfg.camera_port

    win = tk.Toplevel(parent)
    win.title("Clickable Video Feed - Distance Estimation")
    win.transient(parent)

    main_frame = ttk.Frame(win, padding=12)
    main_frame.grid(row=0, column=0, sticky="nsew")
    win.rowconfigure(0, weight=1)
    win.columnconfigure(0, weight=1)

    # Instructions label
    instructions = (
        "1. Click 'Start Video Stream' to open the video window\n"
        "2. Click on the video window where you want to capture coordinates\n"
        "3. Click 'Capture Last Click' to get the coordinates\n"
        "4. Enable 'Auto-send' to automatically send coordinates when captured\n"
        "Or manually enter coordinates (X: 0-3840, Y: 0-2160) below"
    )
    status_label = ttk.Label(main_frame, text=instructions, anchor="center", justify="center")
    status_label.grid(row=0, column=0, sticky="ew", pady=(0, 16))

    # Coordinate input frame
    coord_frame = ttk.LabelFrame(main_frame, text="Click Coordinates", padding=12)
    coord_frame.grid(row=1, column=0, sticky="ew", pady=(0, 16))

    ttk.Label(coord_frame, text="X (0-3840):").grid(row=0, column=0, padx=(0, 8), sticky="w")
    x_entry = ttk.Entry(coord_frame, width=15)
    x_entry.grid(row=0, column=1, padx=(0, 16))

    ttk.Label(coord_frame, text="Y (0-2160):").grid(row=0, column=2, padx=(0, 8), sticky="w")
    y_entry = ttk.Entry(coord_frame, width=15)
    y_entry.grid(row=0, column=3, padx=(0, 16))

    def send_coordinates(x: int, y: int) -> None:
        """Send click coordinates to Jetson."""
        try:
            x_val = int(x)
            y_val = int(y)
            if x_val < 0 or x_val > 3840 or y_val < 0 or y_val > 2160:
                messagebox.showerror(
                    "Invalid Coordinates",
                    f"Coordinates must be:\nX: 0-3840\nY: 0-2160\n\nGot: ({x_val}, {y_val})",
                )
                return

            status_label.config(text=f"Sending click: ({x_val}, {y_val})...")
            resp = send_click(x_val, y_val)
            resp.raise_for_status()
            result = resp.json()
            status_label.config(
                text=f"✓ Sent: ({x_val}, {y_val}) - Status: {result.get('status', 'OK')}"
            )
            print(f"Click sent successfully: {result}")
        except ValueError:
            messagebox.showerror("Invalid Input", "X and Y must be integers.")
        except Exception as exc:  # noqa: BLE001
            err_msg = f"Failed to send click: {exc}"
            status_label.config(text=f"✗ {err_msg}")
            messagebox.showerror("Jetson Error", err_msg)

    def on_manual_send() -> None:
        """Send manually entered coordinates."""
        try:
            x_val = int(x_entry.get().strip())
            y_val = int(y_entry.get().strip())
            send_coordinates(x_val, y_val)
        except ValueError:
            messagebox.showerror("Invalid Input", "X and Y must be integers.")

    auto_send_var = tk.BooleanVar(value=False)

    ttk.Button(coord_frame, text="Send Coordinates", command=on_manual_send).grid(
        row=0, column=4, padx=(8, 0)
    )

    ttk.Checkbutton(
        coord_frame,
        text="Auto-send on capture",
        variable=auto_send_var,
    ).grid(row=0, column=5, padx=(8, 0))

    # Video stream control
    video_frame = ttk.LabelFrame(main_frame, text="Video Stream", padding=12)
    video_frame.grid(row=2, column=0, sticky="ew")

    video_proc: subprocess.Popen | None = None
    click_monitor_running = threading.Event()
    video_window_id: str | None = None
    last_click_position: tuple[int, int] | None = None  # (x, y) screen coordinates

    def find_video_window() -> str | None:
        """Find the GStreamer video window using xdotool."""
        try:
            # Try multiple search strategies
            # First, search by class name (GStreamer windows often have specific classes)
            try:
                result = subprocess.run(
                    ["xdotool", "search", "--class", ".*Gst.*"],
                    capture_output=True,
                    text=True,
                    timeout=2.0,
                )
                window_ids = result.stdout.strip().split("\n")
                for wid in window_ids:
                    if wid and wid.strip():
                        return wid.strip()
            except Exception:
                pass

            # Try searching all windows and checking their properties
            result = subprocess.run(
                ["xdotool", "search", "--name", ".*"],
                capture_output=True,
                text=True,
                timeout=2.0,
            )
            window_ids = result.stdout.strip().split("\n")

            for wid in window_ids:
                if not wid or not wid.strip():
                    continue
                wid = wid.strip()
                try:
                    # Get window name
                    name_result = subprocess.run(
                        ["xdotool", "getwindowname", wid],
                        capture_output=True,
                        text=True,
                        timeout=1.0,
                    )
                    window_name = name_result.stdout.strip().lower()
                    
                    # Get window class
                    class_result = subprocess.run(
                        ["xdotool", "getwindowclassname", wid],
                        capture_output=True,
                        text=True,
                        timeout=1.0,
                    )
                    window_class = class_result.stdout.strip().lower()
                    
                    # GStreamer windows often have "gst", "video", "autovideosink" in name or class
                    if (
                        "gst" in window_name
                        or "video" in window_name
                        or "autovideosink" in window_name
                        or "gst" in window_class
                        or "video" in window_class
                    ):
                        print(f"Found video window: ID={wid}, name='{window_name}', class='{window_class}'")
                        return wid
                except Exception:
                    continue
            
            # If still not found, try searching by PID of the gst-launch process
            if video_proc and video_proc.pid:
                try:
                    # Get all windows and check if any belong to our process
                    result = subprocess.run(
                        ["xdotool", "search", "--pid", str(video_proc.pid)],
                        capture_output=True,
                        text=True,
                        timeout=2.0,
                    )
                    window_ids = result.stdout.strip().split("\n")
                    for wid in window_ids:
                        if wid and wid.strip():
                            print(f"Found video window by PID: {wid.strip()}")
                            return wid.strip()
                except Exception:
                    pass
            
            return None
        except (FileNotFoundError, subprocess.TimeoutExpired, subprocess.CalledProcessError) as e:
            print(f"Error finding video window: {e}")
            return None

    def monitor_clicks() -> None:
        """Monitor for clicks on the video window using xdotool."""
        if video_window_id is None:
            return

        try:
            # Use xdotool to monitor button clicks on the specific window
            # This is more reliable than xinput
            while click_monitor_running.is_set():
                try:
                    # Check if window still exists
                    try:
                        subprocess.run(
                            ["xdotool", "getwindowname", video_window_id],
                            capture_output=True,
                            timeout=0.5,
                            check=True,
                        )
                    except subprocess.CalledProcessError:
                        # Window closed
                        break

                    # Get current active window and mouse position
                    active_result = subprocess.run(
                        ["xdotool", "getactivewindow"],
                        capture_output=True,
                        text=True,
                        timeout=0.5,
                    )
                    active_window = active_result.stdout.strip()

                    # Get window under mouse
                    mouse_window_result = subprocess.run(
                        ["xdotool", "getmouselocation", "--window"],
                        capture_output=True,
                        text=True,
                        timeout=0.5,
                    )
                    mouse_window = mouse_window_result.stdout.strip()

                    # Check if mouse is over our video window
                    if mouse_window == video_window_id or active_window == video_window_id:
                        # Get mouse position
                        mouse_result = subprocess.run(
                            ["xdotool", "getmouselocation", "--shell"],
                            capture_output=True,
                            text=True,
                            timeout=0.5,
                        )

                        mouse_info = {}
                        for mouse_line in mouse_result.stdout.strip().split("\n"):
                            if "=" in mouse_line:
                                key, value = mouse_line.split("=", 1)
                                try:
                                    mouse_info[key] = int(value)
                                except ValueError:
                                    pass

                        if "X" in mouse_info and "Y" in mouse_info:
                            # Store position (we'll check for actual clicks using a different method)
                            nonlocal last_click_position
                            # For now, just store the position when mouse is over window
                            # We'll use a script to actually detect button presses
                            pass

                except Exception as e:
                    print(f"Monitor error: {e}")

                time.sleep(0.1)  # Check every 100ms

        except Exception as e:
            print(f"Click monitor error: {e}")

    def capture_click_at_position(mouse_x: int, mouse_y: int) -> None:
        """Capture click at the given screen coordinates, only if on video window."""
        if video_window_id is None:
            return

        try:
            # First verify which window the mouse is over
            window_at_mouse_result = subprocess.run(
                ["xdotool", "getmouselocation", "--window"],
                capture_output=True,
                text=True,
                timeout=0.5,
            )
            window_at_mouse = window_at_mouse_result.stdout.strip()

            # Only proceed if mouse is over the video window
            if window_at_mouse != video_window_id:
                return  # Silently ignore clicks on other windows

            # Get window geometry
            geom_result = subprocess.run(
                ["xdotool", "getwindowgeometry", video_window_id],
                capture_output=True,
                text=True,
                timeout=2.0,
            )

            geometry = geom_result.stdout
            size_match = re.search(r"Geometry:\s+(\d+)x(\d+)", geometry)
            pos_match = re.search(r"Position:\s+(\d+),(\d+)", geometry)

            if not size_match:
                return

            window_width = int(size_match.group(1))
            window_height = int(size_match.group(2))
            window_x = int(pos_match.group(1)) if pos_match else 0
            window_y = int(pos_match.group(2)) if pos_match else 0

            # Verify mouse is actually within window bounds
            if (
                mouse_x < window_x
                or mouse_x > window_x + window_width
                or mouse_y < window_y
                or mouse_y > window_y + window_height
            ):
                return  # Mouse not in window bounds

            # Calculate relative position within window
            rel_x = mouse_x - window_x
            rel_y = mouse_y - window_y

            # Scale to 4K resolution (3840x2160)
            video_width = 3840
            video_height = 2160

            if window_width > 0 and window_height > 0:
                scaled_x = int((rel_x / window_width) * video_width)
                scaled_y = int((rel_y / window_height) * video_height)
            else:
                scaled_x = rel_x
                scaled_y = rel_y

            # Clamp to valid range
            scaled_x = max(0, min(scaled_x, video_width))
            scaled_y = max(0, min(scaled_y, video_height))

            # Update entry fields
            x_entry.delete(0, tk.END)
            x_entry.insert(0, str(scaled_x))
            y_entry.delete(0, tk.END)
            y_entry.insert(0, str(scaled_y))

            status_label.config(
                text=f"✓ Auto-captured click from video window: ({scaled_x}, {scaled_y})\n"
                "Click 'Send Coordinates' to send to Jetson, or enable auto-send."
            )

            # Auto-send if enabled
            if auto_send_var.get():
                send_coordinates(scaled_x, scaled_y)
        except Exception:
            pass

    def setup_click_capture_script() -> None:
        """Set up a background script to capture clicks on the video window."""
        if video_window_id is None:
            return

        def capture_thread() -> None:
            """Thread that waits for clicks on the video window."""
            try:
                # Use xdotool to wait for a click on the specific window
                # We'll poll periodically and check for clicks
                while click_monitor_running.is_set() and video_window_id:
                    try:
                        # Check if window still exists
                        subprocess.run(
                            ["xdotool", "getwindowname", video_window_id],
                            capture_output=True,
                            timeout=0.5,
                            check=True,
                        )
                    except Exception:
                        break

                    time.sleep(0.2)  # Check every 200ms
            except Exception:
                pass

        threading.Thread(target=capture_thread, daemon=True).start()

    def start_video_stream() -> None:
        """Start the GStreamer UDP video stream."""
        nonlocal video_proc, video_window_id

        if video_proc is not None:
            messagebox.showinfo("Video", "Video stream is already running.")
            return

        cmd = _gstreamer_udp_play_cmd(video_port)

        # Check if gst-launch-1.0 exists
        try:
            subprocess.run(
                ["which", "gst-launch-1.0"],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=2.0,
            )
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            messagebox.showerror(
                "Video Error",
                "gst-launch-1.0 not found. Please install GStreamer:\n"
                "  Ubuntu/Debian: sudo apt install gstreamer1.0-tools gstreamer1.0-plugins-base "
                "gstreamer1.0-plugins-good gstreamer1.0-plugins-bad gstreamer1.0-libav",
            )
            return

        # Check for xdotool (needed for click capture)
        try:
            subprocess.run(
                ["which", "xdotool"],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=2.0,
            )
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            messagebox.showwarning(
                "xdotool Not Found",
                "xdotool is not installed. Click capture on video window will not work.\n"
                "Install with: sudo apt install xdotool\n"
                "You can still manually enter coordinates.",
            )

        try:
            video_proc = subprocess.Popen(
                ["bash", "-lc", cmd],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            # Wait a bit for the window to open, then find it
            def find_window_delayed() -> None:
                time.sleep(2.0)  # Give GStreamer time to open the window
                nonlocal video_window_id
                video_window_id = find_video_window()
                if video_window_id:
                    status_label.config(
                        text=f"Video stream started on UDP port {video_port}.\n"
                        f"Video window found (ID: {video_window_id}).\n"
                        "Click on the video window, then click 'Capture Last Click'.\n"
                        "Or manually enter coordinates above."
                    )
                    # Start click monitoring (for auto-capture if enabled)
                    click_monitor_running.set()
                    threading.Thread(target=monitor_clicks, daemon=True).start()
                    
                    # Also set up a script to capture clicks on the video window
                    setup_click_capture_script()
                else:
                    status_label.config(
                        text=f"Video stream started on UDP port {video_port}.\n"
                        "Video window opened. Click capture may not work.\n"
                        "You can manually enter coordinates above."
                    )

            threading.Thread(target=find_window_delayed, daemon=True).start()

            status_label.config(
                text=f"Video stream starting on UDP port {video_port}.\n"
                "Waiting for video window to open..."
            )
            btn_start_video.config(state="disabled")
            btn_stop_video.config(state="normal")
            btn_capture_click.config(state="normal")
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Video Error", f"Failed to start video pipeline: {exc}")

    def stop_video_stream() -> None:
        """Stop the GStreamer video stream."""
        nonlocal video_proc, video_window_id

        click_monitor_running.clear()

        if video_proc is not None:
            video_proc.terminate()
            try:
                video_proc.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                video_proc.kill()
            video_proc = None
            video_window_id = None
            btn_start_video.config(state="normal")
            btn_stop_video.config(state="disabled")
            btn_capture_click.config(state="disabled")
            status_label.config(text="Video stream stopped.")

    def capture_click() -> None:
        """Capture click position - waits for next click on video window or uses stored position."""
        if video_window_id is None:
            messagebox.showwarning(
                "No Video Window",
                "Video window not found. Please start the video stream first.",
            )
            return

        # Update status to tell user to click
        status_label.config(
            text="Waiting for click on video window...\n"
            "Please click anywhere on the video window now."
        )

        def wait_for_click() -> None:
            """Wait for a click on the video window."""
            nonlocal last_click_position
            try:
                # Use xdotool to get the mouse location when user clicks
                # We'll check periodically if mouse is over video window and was clicked
                for _ in range(50):  # Wait up to 5 seconds (50 * 0.1s)
                    if not click_monitor_running.is_set():
                        return

                    # Check which window mouse is over
                    window_result = subprocess.run(
                        ["xdotool", "getmouselocation", "--window"],
                        capture_output=True,
                        text=True,
                        timeout=0.5,
                    )
                    mouse_window = window_result.stdout.strip()

                    if mouse_window == video_window_id:
                        # Mouse is over video window, get position
                        mouse_result = subprocess.run(
                            ["xdotool", "getmouselocation", "--shell"],
                            capture_output=True,
                            text=True,
                            timeout=0.5,
                        )

                        mouse_info = {}
                        for line in mouse_result.stdout.strip().split("\n"):
                            if "=" in line:
                                key, value = line.split("=", 1)
                                try:
                                    mouse_info[key] = int(value)
                                except ValueError:
                                    pass

                        if "X" in mouse_info and "Y" in mouse_info:
                            # Store and capture
                            last_click_position = (mouse_info["X"], mouse_info["Y"])
                            win.after(0, lambda: capture_click_at_position(
                                mouse_info["X"], mouse_info["Y"]
                            ))
                            return

                    time.sleep(0.1)

                # Timeout - use stored position if available
                win.after(0, lambda: status_label.config(
                    text="Timeout waiting for click.\n"
                    "Click 'Capture Last Click' again and click on the video window."
                ))
            except Exception as e:
                win.after(0, lambda: status_label.config(
                    text=f"Error waiting for click: {e}\n"
                    "Try clicking on the video window and clicking 'Capture Last Click' again."
                ))

        # Start waiting in background thread
        threading.Thread(target=wait_for_click, daemon=True).start()

    btn_start_video = ttk.Button(
        video_frame, text="Start Video Stream", command=start_video_stream
    )
    btn_start_video.grid(row=0, column=0, padx=(0, 8))

    btn_stop_video = ttk.Button(
        video_frame, text="Stop Video Stream", command=stop_video_stream, state="disabled"
    )
    btn_stop_video.grid(row=0, column=1, padx=(0, 8))

    btn_capture_click = ttk.Button(
        video_frame,
        text="Capture Last Click",
        command=capture_click,
        state="disabled",
    )
    btn_capture_click.grid(row=0, column=2)

    def on_closing() -> None:
        stop_video_stream()
        win.destroy()

    win.protocol("WM_DELETE_WINDOW", on_closing)


def open_config_window(parent: tk.Tk) -> None:
    cfg = get_config()

    win = tk.Toplevel(parent)
    win.title("Configuration")
    win.transient(parent)
    win.grab_set()
    win.minsize(420, 360)

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
    add_row(conn, "Jetson IP", "jetson_ip", cfg.jetson_ip, 0)
    add_row(conn, "API Port", "api_port", str(cfg.api_port), 1)
    add_row(conn, "Camera / stream port (UDP)", "camera_port", str(cfg.camera_port), 2)

    net = tab_with_scroll("Network")
    add_row(net, "Moonraker host", "moonraker_host", cfg.moonraker_host, 0)
    add_row(net, "Moonraker port", "moonraker_port", str(cfg.moonraker_port), 1)
    add_row(net, "Moonraker path", "moonraker_path", cfg.moonraker_path, 2)
    add_row(net, "ESP32 IP", "esp32_ip", cfg.esp32_ip, 3)
    add_row(net, "Laptop IP (from API / manual)", "laptop_ip", cfg.laptop_ip, 4)

    mot = tab_with_scroll("Motion")
    motion_fields = [
        ("x_min", "X min"),
        ("x_max", "X max"),
        ("y_min", "Y min"),
        ("y_max", "Y max"),
        ("z_min", "Z min"),
        ("z_max", "Z max"),
        ("neutral_x", "Neutral X"),
        ("neutral_y", "Neutral Y"),
        ("neutral_z", "Neutral Z"),
        ("travel_speed", "Travel speed"),
        ("z_speed", "Z speed"),
        ("send_rate_hz", "Send rate (Hz)"),
        ("feedrate_multiplier", "Feedrate multiplier"),
    ]
    for i, (key, label) in enumerate(motion_fields):
        add_row(mot, label, key, str(getattr(cfg, key)), i)

    def fill_from_cfg() -> None:
        c = get_config()
        for key, w in entries.items():
            w.delete(0, tk.END)
            w.insert(0, str(getattr(c, key)))

    def on_get_from_api() -> None:
        if fetch_and_apply_remote_config(quiet=True):
            fill_from_cfg()
            messagebox.showinfo(
                "Config",
                "Fetched network and motion from the API and saved to config.json.",
            )

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
            for key, _label in motion_fields:
                setattr(c, key, float(entries[key].get().strip()))
            save_config(c)
            net_resp, mot_resp = push_local_config_to_jetson(c)
            net_resp.raise_for_status()
            mot_resp.raise_for_status()
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
            messagebox.showinfo(
                "Config",
                "Saved to config.json and pushed to Jetson (POST /config/network + /config/motion).",
            )
            win.destroy()
        except ValueError as exc:
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
        text="GET /config/network and /config/motion — updates local config.json.",
    ).grid(row=0, column=0, sticky="w", padx=(0, 12))
    ttk.Button(
        api_cfg_frame,
        text="Get config from API",
        command=lambda: fetch_and_apply_remote_config(quiet=False),
    ).grid(row=0, column=1)

    # Button row at the bottom
    button_frame = ttk.Frame(main_frame)
    button_frame.grid(row=4, column=0, sticky="ew")
    for col in range(6):
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

    btn_laser_on = ttk.Button(
        button_frame,
        text="Laser ON",
        command=on_laser_on,
    )
    btn_laser_on.grid(row=0, column=4, sticky="ew", padx=(0, 4))

    btn_laser_off = ttk.Button(
        button_frame,
        text="Laser OFF",
        command=on_laser_off,
    )
    btn_laser_off.grid(row=0, column=5, sticky="ew")

    # Second row for utility buttons
    util_frame = ttk.Frame(main_frame)
    util_frame.grid(row=5, column=0, sticky="ew", pady=(8, 0))
    for col in range(6):
        util_frame.columnconfigure(col, weight=1)

    btn_video = ttk.Button(
        util_frame,
        text="Open Video",
        command=on_open_video,
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

