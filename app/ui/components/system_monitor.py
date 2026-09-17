"""System resource monitor bar (CPU / GPU / Disk / Net).

Extracted from AppWindow to shrink the god class.
Owns its own widgets, history, and update loop.
"""

from __future__ import annotations

import platform
import subprocess
from typing import Any, Callable, Optional

import customtkinter as ctk

from app.ui.themes import UI as _UI
from app.ui.components.widget_names import (
    build_name,
    set_widget_name,
    name_system_monitor_metric,
    REGION_SYSTEM_MONITOR,
    PREFIX_FRAME,
    PREFIX_LABEL,
)


class SystemMonitorBar:
    """Top-of-content system resource bar with mini sparklines."""

    METRICS = [
        ("cpu", "CPU", "🖥", ("#3b82f6", "#60a5fa")),
        ("gpu", "GPU", "🎮", ("#8b5cf6", "#a78bfa")),
        ("disk", "DISK", "💾", ("#f59e0b", "#fbbf24")),
        ("net", "NET", "📡", ("#10b981", "#34d399")),
    ]

    def __init__(
        self,
        parent: ctk.CTkBaseClass,
        *,
        after: Callable[[int, Callable], Any],
        on_toggle: Optional[Callable[[], None]] = None,
    ) -> None:
        self._parent = parent
        self._after = after
        self._on_toggle = on_toggle

        self.frame: Optional[ctk.CTkFrame] = None
        self.collapsed = False
        self._running = False

        self._labels: dict[str, ctk.CTkLabel] = {}
        self._graphs: dict[str, ctk.CTkFrame] = {}
        self._history: dict[str, list[float]] = {k: [] for k, _, _, _ in self.METRICS}
        self._max_points = 50

        self._net_down_label: Optional[ctk.CTkLabel] = None
        self._net_up_label: Optional[ctk.CTkLabel] = None
        self._disk_read_label: Optional[ctk.CTkLabel] = None
        self._disk_write_label: Optional[ctk.CTkLabel] = None

        self._last_net_sent = 0
        self._last_net_recv = 0
        self._last_disk_read = 0
        self._last_disk_write = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build(self) -> ctk.CTkFrame:
        """Create the bar and place it in the parent (row=0)."""
        self.frame = ctk.CTkFrame(
            self._parent,
            height=42,
            corner_radius=0,
            fg_color=_UI["top_bg"],
            border_width=1,
            border_color=_UI["top_border"],
        )
        self.frame.grid(row=0, column=0, sticky="ew")
        self.frame.grid_propagate(False)
        self.frame.grid_columnconfigure(0, weight=1)
        set_widget_name(self.frame, build_name("app", REGION_SYSTEM_MONITOR, PREFIX_FRAME, "bar"))

        inner = ctk.CTkFrame(self.frame, fg_color="transparent")
        inner.pack(fill="x", padx=12, pady=4)
        set_widget_name(inner, build_name("app", REGION_SYSTEM_MONITOR, PREFIX_FRAME, "inner"))

        for key, label, icon, color in self.METRICS:
            mframe = ctk.CTkFrame(inner, fg_color="transparent")
            mframe.pack(side="left", fill="y", padx=(0, 16))
            set_widget_name(mframe, name_system_monitor_metric(key))

            top_row = ctk.CTkFrame(mframe, fg_color="transparent")
            top_row.pack(fill="x")

            ctk.CTkLabel(
                top_row,
                text=f"{icon} {label}",
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color=_UI["label"],
            ).pack(side="left")

            pct_label = ctk.CTkLabel(
                top_row,
                text="0%",
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color=color[1],
                width=40,
            )
            pct_label.pack(side="right", padx=(4, 0))
            self._labels[key] = pct_label
            set_widget_name(pct_label, build_name("app", REGION_SYSTEM_MONITOR, PREFIX_LABEL, f"{key}_pct"))

            if key in ("net", "disk"):
                speed_row = ctk.CTkFrame(mframe, fg_color="transparent")
                speed_row.pack(fill="x", pady=(0, 0))

                if key == "net":
                    self._net_down_label = ctk.CTkLabel(
                        speed_row,
                        text="↓ 0.0 Mbps",
                        font=ctk.CTkFont(size=9),
                        text_color=("#10b981", "#34d399"),
                    )
                    self._net_down_label.pack(side="left", padx=(2, 8))
                    set_widget_name(self._net_down_label, build_name("app", REGION_SYSTEM_MONITOR, PREFIX_LABEL, "net_down"))

                    self._net_up_label = ctk.CTkLabel(
                        speed_row,
                        text="↑ 0.0 Mbps",
                        font=ctk.CTkFont(size=9),
                        text_color=("#ef4444", "#f87171"),
                    )
                    self._net_up_label.pack(side="left")
                    set_widget_name(self._net_up_label, build_name("app", REGION_SYSTEM_MONITOR, PREFIX_LABEL, "net_up"))
                else:
                    self._disk_read_label = ctk.CTkLabel(
                        speed_row,
                        text="R 0.0 MB/s",
                        font=ctk.CTkFont(size=9),
                        text_color=("#3b82f6", "#60a5fa"),
                    )
                    self._disk_read_label.pack(side="left", padx=(2, 8))
                    set_widget_name(self._disk_read_label, build_name("app", REGION_SYSTEM_MONITOR, PREFIX_LABEL, "disk_read"))

                    self._disk_write_label = ctk.CTkLabel(
                        speed_row,
                        text="W 0.0 MB/s",
                        font=ctk.CTkFont(size=9),
                        text_color=("#f59e0b", "#fbbf24"),
                    )
                    self._disk_write_label.pack(side="left")
                    set_widget_name(self._disk_write_label, build_name("app", REGION_SYSTEM_MONITOR, PREFIX_LABEL, "disk_write"))

            graph_frame = ctk.CTkFrame(
                mframe,
                height=18,
                fg_color=_UI["top_bg"],
                corner_radius=3,
                border_width=0,
            )
            graph_frame.pack(fill="x", pady=(2, 0))
            graph_frame.pack_propagate(False)
            self._graphs[key] = graph_frame
            set_widget_name(graph_frame, build_name("app", REGION_SYSTEM_MONITOR, PREFIX_FRAME, f"{key}_graph"))

        self._running = True
        self._update()
        return self.frame

    def set_collapsed(self, hidden: bool) -> None:
        self.collapsed = bool(hidden)
        if self.frame is None:
            return
        try:
            if hidden:
                self.frame.grid_remove()
            else:
                self.frame.grid()
        except Exception:
            pass

    def toggle(self) -> bool:
        """Toggle visibility. Returns new collapsed state."""
        self.set_collapsed(not self.collapsed)
        return self.collapsed

    def stop(self) -> None:
        self._running = False

    def _update(self) -> None:
        if not self._running:
            return
        try:
            if self.frame is None or not self.frame.winfo_exists():
                return
        except Exception:
            return

        try:
            import psutil

            cpu_pct = psutil.cpu_percent(interval=None)

            gpu_pct = 0.0
            try:
                result = subprocess.run(
                    ["nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"],
                    capture_output=True,
                    text=True,
                    timeout=1.0,
                )
                if result.returncode == 0:
                    vals = [float(x.strip()) for x in result.stdout.strip().split("\n") if x.strip()]
                    gpu_pct = sum(vals) / len(vals) if vals else 0.0
            except Exception:
                pass

            disk_pct = 0.0
            disk_read_mbps = 0.0
            disk_write_mbps = 0.0
            try:
                path = "C:\\" if platform.system() == "Windows" else "/"
                disk = psutil.disk_usage(path)
                disk_pct = disk.percent
                disk_io = psutil.disk_io_counters()
                if disk_io:
                    cur_r, cur_w = disk_io.read_bytes, disk_io.write_bytes
                    if self._last_disk_read or self._last_disk_write:
                        disk_read_mbps = (cur_r - self._last_disk_read) / 1024 / 1024 / 2
                        disk_write_mbps = (cur_w - self._last_disk_write) / 1024 / 1024 / 2
                    self._last_disk_read = cur_r
                    self._last_disk_write = cur_w
            except Exception:
                pass

            net_pct = 0.0
            net_down_mbps = 0.0
            net_up_mbps = 0.0
            try:
                net_io = psutil.net_io_counters()
                cur_sent, cur_recv = net_io.bytes_sent, net_io.bytes_recv
                if self._last_net_sent or self._last_net_recv:
                    up_delta = cur_sent - self._last_net_sent
                    down_delta = cur_recv - self._last_net_recv
                    net_up_mbps = up_delta * 8 / 1024 / 1024 / 2
                    net_down_mbps = down_delta * 8 / 1024 / 1024 / 2
                    net_pct = min(100.0, ((up_delta + down_delta) / 1024 / 1024) * 10)
                self._last_net_sent = cur_sent
                self._last_net_recv = cur_recv
            except Exception:
                pass

            values = {
                "cpu": cpu_pct,
                "gpu": gpu_pct,
                "disk": disk_pct,
                "net": net_pct,
            }

            for key, _, _, color in self.METRICS:
                val = values.get(key, 0.0)
                hist = self._history[key]
                hist.append(val)
                if len(hist) > self._max_points:
                    hist.pop(0)

                label = self._labels.get(key)
                if label is not None:
                    try:
                        if label.winfo_exists():
                            label.configure(text=f"{val:.0f}%", text_color=color[1])
                    except Exception:
                        pass

                graph = self._graphs.get(key)
                if graph is not None:
                    self._draw_mini_graph(graph, hist, key)

            if self._net_down_label is not None:
                try:
                    if self._net_down_label.winfo_exists():
                        self._net_down_label.configure(text=f"↓ {net_down_mbps:.1f} Mbps")
                except Exception:
                    pass
            if self._net_up_label is not None:
                try:
                    if self._net_up_label.winfo_exists():
                        self._net_up_label.configure(text=f"↑ {net_up_mbps:.1f} Mbps")
                except Exception:
                    pass
            if self._disk_read_label is not None:
                try:
                    if self._disk_read_label.winfo_exists():
                        self._disk_read_label.configure(text=f"R {disk_read_mbps:.1f} MB/s")
                except Exception:
                    pass
            if self._disk_write_label is not None:
                try:
                    if self._disk_write_label.winfo_exists():
                        self._disk_write_label.configure(text=f"W {disk_write_mbps:.1f} MB/s")
                except Exception:
                    pass

        except Exception:
            pass

        try:
            self._after(2000, self._update)
        except Exception:
            pass

    def _draw_mini_graph(self, graph_frame: ctk.CTkFrame, history: list[float], key: str) -> None:
        if not history:
            return
        try:
            for w in graph_frame.winfo_children():
                try:
                    w.destroy()
                except Exception:
                    pass
            if len(history) < 2:
                return

            metric_colors = {
                "cpu": ("#3b82f6", "#60a5fa"),
                "gpu": ("#8b5cf6", "#a78bfa"),
                "disk": ("#f59e0b", "#fbbf24"),
                "net": ("#10b981", "#34d399"),
            }
            color = metric_colors.get(key, ("#64748b", "#94a3b8"))[1]
            width, height, padding = 120, 16, 2
            max_val = max(max(history), 1)
            bar_width = max(1, width // len(history))

            for i, val in enumerate(history):
                bar_height = max(1, int((val / max_val) * (height - padding * 2)))
                bar = ctk.CTkFrame(
                    graph_frame,
                    width=bar_width,
                    height=bar_height,
                    fg_color=color,
                    corner_radius=0,
                )
                bar.place(x=i * bar_width, y=height - padding - bar_height)
        except Exception:
            pass
