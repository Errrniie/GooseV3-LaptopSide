"""Clickable video dialog: Tk + TCP JPEG stream + PIL; clicks map to 3840×2160 for send_click."""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from config import get_config
from gui.tk_gst_video import TkGstVideoWidget
from jetson_client import send_click


def open_clickable_video_window(parent: tk.Tk) -> None:
    cfg = get_config()
    video_port = cfg.camera_port

    win = tk.Toplevel(parent)
    win.title("Clickable Video Feed - Distance Estimation")
    win.transient(parent)
    win.geometry("960x600")

    main_frame = ttk.Frame(win, padding=12)
    main_frame.grid(row=0, column=0, sticky="nsew")
    win.rowconfigure(0, weight=1)
    win.columnconfigure(0, weight=1)
    main_frame.rowconfigure(2, weight=1)
    main_frame.columnconfigure(0, weight=1)

    instructions = (
        "1. Click 'Start Video Stream' to play video in the pane below.\n"
        "2. Click directly on the video to capture coordinates (mapped to 3840×2160).\n"
        "3. Use 'Send Coordinates' or enable auto-send to send to the Jetson.\n"
        "You can also type X/Y manually."
    )
    status_label = ttk.Label(main_frame, text=instructions, anchor="center", justify="center")
    status_label.grid(row=0, column=0, sticky="ew", pady=(0, 16))

    coord_frame = ttk.LabelFrame(main_frame, text="Click Coordinates", padding=12)
    coord_frame.grid(row=1, column=0, sticky="ew", pady=(0, 16))

    ttk.Label(coord_frame, text="X (0-3840):").grid(row=0, column=0, padx=(0, 8), sticky="w")
    x_entry = ttk.Entry(coord_frame, width=15)
    x_entry.grid(row=0, column=1, padx=(0, 16))

    ttk.Label(coord_frame, text="Y (0-2160):").grid(row=0, column=2, padx=(0, 8), sticky="w")
    y_entry = ttk.Entry(coord_frame, width=15)
    y_entry.grid(row=0, column=3, padx=(0, 16))

    def send_coordinates(x: int, y: int) -> None:
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

    video_frame = ttk.LabelFrame(main_frame, text="Video Stream", padding=12)
    video_frame.grid(row=2, column=0, sticky="nsew", pady=(0, 16))
    video_frame.rowconfigure(0, weight=1)
    video_frame.columnconfigure(0, weight=1)

    video_display = ttk.Frame(video_frame)
    video_display.grid(row=0, column=0, sticky="nsew", pady=(0, 12))

    btn_row = ttk.Frame(video_frame)
    btn_row.grid(row=1, column=0, sticky="ew")

    player: TkGstVideoWidget | None = None

    def on_video_click(event: tk.Event) -> None:  # type: ignore[type-arg]
        nonlocal player
        if player is None:
            return
        sx, sy = player.event_xy_to_native(event.x, event.y)
        x_entry.delete(0, tk.END)
        x_entry.insert(0, str(sx))
        y_entry.delete(0, tk.END)
        y_entry.insert(0, str(sy))
        status_label.config(
            text=f"✓ Captured click on video: ({sx}, {sy})\n"
            "Send manually or enable auto-send to send to Jetson."
        )
        if auto_send_var.get():
            send_coordinates(sx, sy)

    def start_video_stream() -> None:
        nonlocal player
        if player is not None:
            messagebox.showinfo("Video", "Video stream is already running.")
            return

        p = TkGstVideoWidget(video_display, video_port, draw_bbox=True)
        p.label.pack(fill=tk.BOTH, expand=True)
        p.label.bind("<Button-1>", on_video_click)

        ok, err = p.start()
        if not ok:
            p.label.destroy()
            messagebox.showerror(
                "Video Error",
                f"Could not start video stream.\n\n{err}\n\n"
                "Install: opencv-python-headless, numpy, Pillow.\n"
                "Arch: sudo pacman -S python-opencv python-numpy python-pillow",
            )
            return

        player = p
        status_label.config(
            text=f"Video playing (TCP JPEG) {cfg.jetson_ip}:{video_port}.\n"
            "Click on the video to capture coordinates."
        )
        btn_start_video.config(state="disabled")
        btn_stop_video.config(state="normal")

    def stop_video_stream() -> None:
        nonlocal player
        if player is not None:
            player.stop()
            player.label.destroy()
            player = None
        btn_start_video.config(state="normal")
        btn_stop_video.config(state="disabled")
        status_label.config(text="Video stream stopped.")

    btn_start_video = ttk.Button(btn_row, text="Start Video Stream", command=start_video_stream)
    btn_start_video.grid(row=0, column=0, padx=(0, 8))

    btn_stop_video = ttk.Button(
        btn_row, text="Stop Video Stream", command=stop_video_stream, state="disabled"
    )
    btn_stop_video.grid(row=0, column=1, padx=(0, 8))

    def on_closing() -> None:
        stop_video_stream()
        win.destroy()

    win.protocol("WM_DELETE_WINDOW", on_closing)
