"""
TCP length-prefixed JPEG stream → OpenCV decode (BGR) → pygame window.

Wire format per frame: 4-byte big-endian length (``>I``), then JPEG bytes.
Overlay is drawn with OpenCV on the BGR frame before display.
Requires: opencv-python, numpy, pygame.
"""
from __future__ import annotations

import json
import queue
import socket
import struct
import threading
import time
import tkinter as tk
from typing import Any, Callable, Dict, Optional, Tuple

import numpy as np

from gui.vision_bbox import parse_overlay_boxes
from jetson_client import get_vision_detection

try:
    import cv2
except ImportError:
    cv2 = None  # type: ignore[assignment]

try:
    import pygame
except ImportError:
    pygame = None  # type: ignore[assignment]

_MAX_JPEG_BYTES = 50 * 1024 * 1024


class TkGstVideoWidget:
    """
    Receive frames over TCP and render in a pygame window.
    The ``label`` attribute is kept for backwards compatibility with the existing Tk UI.
    """

    def __init__(
        self,
        parent: tk.Widget,
        video_port: int,
        *,
        jetson_ip: Optional[str] = None,
        draw_bbox: bool = True,
        poll_ms: int = 100,
        on_native_frame_size: Optional[Callable[[int, int], None]] = None,
    ) -> None:
        self._parent = parent
        self._master = parent.winfo_toplevel()
        self.video_port = video_port
        if jetson_ip is not None:
            self._jetson_ip = jetson_ip.strip()
        else:
            from config import get_config

            self._jetson_ip = get_config().jetson_ip.strip()
        self.draw_bbox = draw_bbox
        self.poll_ms = poll_ms
        self._on_native_frame_size = on_native_frame_size

        self.label = tk.Label(parent, bg="black", cursor="crosshair")

        self._frame_queue: queue.Queue[np.ndarray] = queue.Queue(maxsize=2)
        self._bbox_lock = threading.Lock()
        self._bbox_data: Dict[str, Any] = {}

        self._running = False
        self._sock: Optional[socket.socket] = None
        self._sock_lock = threading.Lock()
        self._pygame_thread: Optional[threading.Thread] = None
        self._stream_thread: Optional[threading.Thread] = None
        self._poll_thread: Optional[threading.Thread] = None

        self.native_w = 0
        self.native_h = 0
        self.display_w = 0
        self.display_h = 0
        self.decoder_label: str = ""

    def start(self) -> tuple[bool, str]:
        if cv2 is None:
            return (
                False,
                "OpenCV is required for TCP video. Install: pip install opencv-python-headless",
            )
        if pygame is None:
            return (
                False,
                "pygame is required for rendering. Install: pip install pygame",
            )
        if self._running:
            return True, ""

        self._running = True
        self.decoder_label = "TCP JPEG (OpenCV)"

        self._stream_thread = threading.Thread(
            target=self._tcp_recv_loop, daemon=True, name="tcp-video-stream"
        )
        self._stream_thread.start()

        if self.draw_bbox:
            self._poll_thread = threading.Thread(
                target=self._poll_bbox_loop, daemon=True, name="vision-detection-poll"
            )
            self._poll_thread.start()

        self._pygame_thread = threading.Thread(
            target=self._pygame_loop, daemon=True, name="pygame-render"
        )
        self._pygame_thread.start()

        self.label.config(text="(Rendering in pygame window)")
        return True, ""

    def _tcp_recv_loop(self) -> None:
        assert cv2 is not None
        addr = (self._jetson_ip, int(self.video_port))
        reconnect_sleep_s = 0.5

        def _close_socket(s: socket.socket) -> None:
            try:
                s.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                s.close()
            except OSError:
                pass

        while self._running:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            with self._sock_lock:
                self._sock = sock
            try:
                sock.settimeout(2.0)
                try:
                    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                except OSError:
                    pass
                try:
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
                except OSError:
                    pass

                sock.connect(addr)

                frame_count = 0

                def recv_exact(n: int) -> bytes:
                    buf = b""
                    while len(buf) < n:
                        chunk = sock.recv(n - len(buf))
                        if not chunk:
                            raise ConnectionError("Jetson disconnected")
                        buf += chunk
                    return buf

                while self._running:
                    raw_len = recv_exact(4)
                    size = struct.unpack(">I", raw_len)[0]
                    if size == 0 or size > _MAX_JPEG_BYTES:
                        raise ConnectionError(f"Bad frame size {size}")
                    data = recv_exact(size)
                    frame = cv2.imdecode(
                        np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR
                    )
                    self._on_frame(frame)
                    frame_count += 1
                    if frame_count % 30 == 0:
                        try:
                            qsz = self._frame_queue.qsize()
                        except Exception:
                            qsz = -1
                        print(
                            f"[STREAM] Frames received: {frame_count}, queue size: {qsz}",
                            flush=True,
                        )
            except socket.timeout:
                pass
            except ConnectionError as exc:
                _ = exc
            except OSError as exc:
                _ = exc
            except Exception as exc:  # noqa: BLE001
                _ = exc
            finally:
                _close_socket(sock)
                with self._sock_lock:
                    if self._sock is sock:
                        self._sock = None
            if self._running:
                time.sleep(reconnect_sleep_s)

    def _on_frame(self, frame: Any) -> None:
        """BGR numpy (OpenCV) → enqueue for pygame rendering."""
        if frame is None or not hasattr(frame, "size") or frame.size == 0:
            return
        try:
            self._frame_queue.put_nowait(frame)
        except queue.Full:
            try:
                self._frame_queue.get_nowait()
            except queue.Empty:
                pass
            try:
                self._frame_queue.put_nowait(frame)
            except queue.Full:
                pass

    def stop(self) -> None:
        self._running = False

        with self._sock_lock:
            s = self._sock
            self._sock = None
        if s is not None:
            try:
                s.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                s.close()
            except OSError:
                pass

        if self._stream_thread is not None and self._stream_thread.is_alive():
            self._stream_thread.join(timeout=2.0)
        self._stream_thread = None

        if self._pygame_thread is not None and self._pygame_thread.is_alive():
            self._pygame_thread.join(timeout=2.0)
        self._pygame_thread = None

        if self._poll_thread is not None and self._poll_thread.is_alive():
            self._poll_thread.join(timeout=1.0)
        self._poll_thread = None

        while True:
            try:
                self._frame_queue.get_nowait()
            except queue.Empty:
                break

        self.label.config(text="")

    def _poll_bbox_loop(self) -> None:
        while self._running:
            try:
                data = get_vision_detection(timeout=2.0)
                payload = dict(data) if isinstance(data, dict) else {}
                with self._bbox_lock:
                    self._bbox_data = payload
            except Exception as exc:
                _ = exc
            time.sleep(self.poll_ms / 1000.0)

    def _pygame_loop(self) -> None:
        """Run pygame event/render loop in a background thread."""
        assert pygame is not None
        assert cv2 is not None

        pygame.init()
        try:
            screen = pygame.display.set_mode((1280, 720), pygame.RESIZABLE)
            pygame.display.set_caption("GooseV3")
        except Exception as exc:  # noqa: BLE001
            print(f"[RENDER] pygame init/display failed: {exc}", flush=True)
            self._running = False
            return
        clock = pygame.time.Clock()

        render_count = 0

        while self._running:
            try:
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        self._running = False
                        break
            except Exception as exc:  # noqa: BLE001
                print(f"[RENDER] pygame event error: {exc}", flush=True)
                clock.tick(30)
                continue

            try:
                frame = self._frame_queue.get(timeout=1.0)
            except queue.Empty:
                print("[RENDER] Queue empty - waiting for frame", flush=True)
                clock.tick(30)
                continue

            render_count += 1
            if render_count % 30 == 0:
                try:
                    qsz = self._frame_queue.qsize()
                except Exception:
                    qsz = -1
                print(
                    f"[RENDER] frames_rendered={render_count} queue={qsz}",
                    flush=True,
                )

            try:
                # Validate frame
                if not isinstance(frame, np.ndarray):
                    continue
                if frame.ndim != 3 or frame.shape[2] < 3:
                    continue

                # Defensive copy so downstream operations don't corrupt queued frames
                frame = frame.copy()

                h, w = frame.shape[:2]

                self.native_w = int(w)
                self.native_h = int(h)
                if self._on_native_frame_size:
                    try:
                        self._master.after(
                            0, lambda: self._on_native_frame_size(int(w), int(h))
                        )
                    except Exception:
                        pass

                if self.draw_bbox:
                    with self._bbox_lock:
                        data = dict(self._bbox_data)
                    boxes, fw, fh = parse_overlay_boxes(data)
                    if boxes and fw > 0 and fh > 0:
                        sx = float(w) / float(fw)
                        sy = float(h) / float(fh)
                        for x0, y0, bw, bh, color, is_active in boxes:
                            x1 = int(x0 * sx)
                            y1 = int(y0 * sy)
                            x2 = int((x0 + bw) * sx)
                            y2 = int((y0 + bh) * sy)
                            thickness = 4 if is_active else 2
                            bgr = (0, 255, 255)
                            c = str(color).lower()
                            if c in ("red", "#ff0000"):
                                bgr = (0, 0, 255)
                            elif c in ("#00cc00", "green", "#00ff00"):
                                bgr = (0, 255, 0)
                            cv2.rectangle(frame, (x1, y1), (x2, y2), bgr, thickness)

                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                surface = pygame.surfarray.make_surface(rgb.swapaxes(0, 1))
                scaled = pygame.transform.scale(surface, screen.get_size())
                screen.blit(scaled, (0, 0))
                pygame.display.flip()
                try:
                    self.display_w, self.display_h = screen.get_size()
                except Exception:
                    pass
            except Exception as exc:  # noqa: BLE001
                # If pygame/SDL gets into a bad state, recreate the window.
                print(f"[RENDER] render error: {exc}", flush=True)
                try:
                    screen = pygame.display.set_mode(screen.get_size(), pygame.RESIZABLE)
                except Exception:
                    pass

            clock.tick(60)

        try:
            pygame.quit()
        except Exception:
            pass

    def event_xy_to_native(
        self, event_x: int, event_y: int, video_width: int = 3840, video_height: int = 2160
    ) -> Tuple[int, int]:
        """Map click on label (display pixels) to Jetson click coordinates."""
        lw = max(1, self.label.winfo_width())
        lh = max(1, self.label.winfo_height())
        dw = max(1, self.display_w)
        dh = max(1, self.display_h)
        nx = max(0, self.native_w)
        ny = max(0, self.native_h)
        if nx == 0 or ny == 0:
            nx, ny = dw, dh

        # Stretched: image fills label; fallback: centered smaller image
        if abs(lw - dw) <= 2 and abs(lh - dh) <= 2:
            ox, oy = 0, 0
        else:
            ox = (lw - dw) // 2
            oy = (lh - dh) // 2
        lx = event_x - ox
        ly = event_y - oy
        lx = max(0, min(dw - 1, lx))
        ly = max(0, min(dh - 1, ly))

        frame_x = int(lx * nx / dw)
        frame_y = int(ly * ny / dh)

        out_x = int(frame_x * video_width / nx) if nx else 0
        out_y = int(frame_y * video_height / ny) if ny else 0
        out_x = max(0, min(video_width, out_x))
        out_y = max(0, min(video_height, out_y))
        return out_x, out_y
