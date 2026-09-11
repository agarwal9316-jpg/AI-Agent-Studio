"""Mission Control — detailed ops monitoring GUI."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import customtkinter as ctk

from app.ui.themes import UI as _UI
from app.ui.themes import style_chrome_button, style_card

if TYPE_CHECKING:
    from app.ui.app_window import AppWindow

_HC_MUTED = _UI["muted"]
_HC_LABEL = _UI["label"]


def page_monitor(app: AppWindow) -> None:
    from app.services import ops_monitor as ops
    from app.core.services.data.usage_meter import format_status_line
    from app.ui.components.layman_copy import (
        MONITOR_EVENTS,
        MONITOR_SYSTEM,
        MONITOR_ALERTS,
        MONITOR_JOBS,
        MONITOR_NO_EVENTS,
        MONITOR_NO_JOBS,
    )

    simple = bool(getattr(app, "_is_simple_ui", lambda: True)())

    root = ctk.CTkFrame(app.content, fg_color="transparent")
    root.grid(row=0, column=0, sticky="nsew", padx=12, pady=12)
    root.grid_columnconfigure(0, weight=1)

    app._page_header(
        root,
        "Activity",
        (
            "See if the AI is busy. Press Refresh if something looks stuck."
            if simple
            else "Ops monitor: system, tokens, train jobs, and event log."
        ),
        actions=[
            ("Refresh now", lambda: paint()),
            ("← Start", lambda: app.show_page("Home")),
        ],
    )

    r = 1
    if simple:
        tip = ctk.CTkFrame(
            root, fg_color=_UI.get("accent_soft", ("#dbeafe", "#1e293b")), corner_radius=10
        )
        tip.grid(row=r, column=0, sticky="ew", pady=(0, 8))
        r += 1
        ctk.CTkLabel(
            tip,
            text="Tip: Open this while Chat or Team is running. Green numbers mean things look healthy.",
            text_color=_HC_LABEL,
            font=ctk.CTkFont(size=12),
            anchor="w",
        ).pack(fill="x", padx=14, pady=10)

    # KPI strip
    kpi = ctk.CTkFrame(root, **style_card())
    kpi.grid(row=r, column=0, sticky="ew", pady=(0, 8))
    r += 1
    kpi_labels: list[ctk.CTkLabel] = []
    for _ in range(8):  # Added 2 more for Disk I/O and Network I/O
        lb = ctk.CTkLabel(kpi, text="—", text_color=_HC_LABEL, font=ctk.CTkFont(size=11))
        lb.pack(side="left", padx=12, pady=10)
        kpi_labels.append(lb)

    body = ctk.CTkFrame(root, fg_color="transparent")
    body.grid(row=r, column=0, sticky="nsew")
    root.grid_rowconfigure(r, weight=1)
    body.grid_columnconfigure(0, weight=2)
    body.grid_columnconfigure(1, weight=1)
    body.grid_rowconfigure(0, weight=1)

    # Events
    left = ctk.CTkFrame(body, **style_card())
    left.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
    left.grid_rowconfigure(1, weight=1)
    ctk.CTkLabel(
        left,
        text=MONITOR_EVENTS if simple else "Ops event log",
        font=ctk.CTkFont(size=14, weight="bold"),
        text_color=_HC_LABEL,
    ).grid(row=0, column=0, sticky="w", padx=12, pady=8)
    log_box = ctk.CTkTextbox(
        left,
        font=ctk.CTkFont(family="Consolas" if not simple else "Segoe UI", size=12 if simple else 12),
    )
    log_box.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))

    # Right: hardware + jobs + alerts
    right = ctk.CTkFrame(body, **style_card())
    right.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
    right.grid_rowconfigure(3, weight=1)
    ctk.CTkLabel(
        right,
        text=MONITOR_SYSTEM if simple else "System",
        font=ctk.CTkFont(size=14, weight="bold"),
        text_color=_HC_LABEL,
    ).pack(anchor="w", padx=12, pady=(10, 4))
    hw_lbl = ctk.CTkLabel(right, text="", text_color=_HC_MUTED, justify="left", wraplength=280, anchor="w")
    hw_lbl.pack(anchor="w", padx=12, pady=4)
    ctk.CTkLabel(
        right,
        text=MONITOR_ALERTS if simple else "Alerts",
        font=ctk.CTkFont(size=13, weight="bold"),
        text_color=_HC_LABEL,
    ).pack(anchor="w", padx=12, pady=(10, 2))
    alert_lbl = ctk.CTkLabel(right, text="", text_color=_UI.get("warning", _HC_MUTED), justify="left", wraplength=280, anchor="w")
    alert_lbl.pack(anchor="w", padx=12, pady=2)
    ctk.CTkLabel(
        right,
        text=MONITOR_JOBS if simple else "Train jobs",
        font=ctk.CTkFont(size=13, weight="bold"),
        text_color=_HC_LABEL,
    ).pack(anchor="w", padx=12, pady=(10, 2))
    jobs_box = ctk.CTkTextbox(right, height=160, font=ctk.CTkFont(size=11))
    jobs_box.pack(fill="both", expand=True, padx=8, pady=8)

    def paint() -> None:
        try:
            s = ops.mission_summary()
        except Exception as e:
            # Fallback: at least show something
            s = {}
            for lb in kpi_labels:
                lb.configure(text="⚠ error")
            return
        u = s.get("usage") or {}
        tot = (u.get("totals") or {}) if isinstance(u, dict) else {}
        hw = s.get("hardware") or {}
        ram = hw.get("ram") or {}
        gpu = (hw.get("gpu") or [{}])[0] if hw.get("gpu") else {}
        disk = hw.get("disk") or {}
        net = hw.get("net") or {}
        proc = hw.get("process") or {}

        if simple:
            bits = [
                f"Words used ~{int(tot.get('total_tokens') or 0):,}",
                f"Est. cost ${float(tot.get('est_cost_usd') or 0):.3f}",
                f"Computer busy {hw.get('cpu_percent') if hw.get('cpu_percent') is not None else '?'}%",
                f"RAM {ram.get('used_gb', 0):.1f}/{ram.get('total_gb', 0):.1f} GB ({ram.get('percent', '?')}%)",
                f"Graphics {gpu.get('util_percent', '—')}%",
                f"Disk R/W {disk.get('read_mb', 0):.1f}/{disk.get('write_mb', 0):.1f} MB",
                f"Net S/R {net.get('sent_mb', 0):.1f}/{net.get('recv_mb', 0):.1f} MB",
                f"Saved AIs {s.get('model_profiles')} · Goals {s.get('team_channels')}",
            ]
        else:
            bits = [
                f"Tokens {int(tot.get('total_tokens') or 0):,}",
                f"Est ${float(tot.get('est_cost_usd') or 0):.3f}",
                f"CPU {hw.get('cpu_percent') if hw.get('cpu_percent') is not None else '?'}%",
                f"RAM {ram.get('used_gb', 0):.1f}/{ram.get('total_gb', 0):.1f} GB ({ram.get('percent', '?')}%)",
                f"GPU {gpu.get('util_percent', '—')}%",
                f"Disk R/W {disk.get('read_mb', 0):.1f}/{disk.get('write_mb', 0):.1f} MB",
                f"Net S/R {net.get('sent_mb', 0):.1f}/{net.get('recv_mb', 0):.1f} MB",
                f"Profiles {s.get('model_profiles')} · Team {s.get('team_channels')}",
            ]
        for lb, t in zip(kpi_labels, bits):
            try:
                lb.configure(text=t)
            except Exception:
                pass

        # hardware detail
        if simple:
            hw_lbl.configure(
                text=(
                    f"How busy is the computer: {hw.get('cpu_percent')}%\n"
                    f"Memory used: {ram.get('used_gb')}/{ram.get('total_gb')} GB ({ram.get('percent')}%)\n"
                    f"Graphics card: {gpu.get('util_percent', 'not shown')}%\n"
                    f"Disk I/O: R {disk.get('read_mb', 0):.1f} MB / W {disk.get('write_mb', 0):.1f} MB\n"
                    f"Network I/O: Sent {net.get('sent_mb', 0):.1f} MB / Recv {net.get('recv_mb', 0):.1f} MB\n"
                    f"Process: CPU {proc.get('cpu_percent', '?')}% · Mem {proc.get('mem_mb', '?')} MB · Threads {proc.get('threads', '?')}\n\n"
                    f"Usage: {format_status_line()}"
                )
            )
        else:
            gpu_lines = []
            for g in hw.get("gpu") or []:
                gpu_lines.append(
                    f"{g.get('name')}: util {g.get('util_percent')}% · "
                    f"VRAM {g.get('mem_used_mb')}/{g.get('mem_total_mb')} MB"
                )
            if not gpu_lines:
                gpu_lines = ["GPU: (no nvidia-smi)"]
            hw_lbl.configure(
                text=(
                    f"CPU: {hw.get('cpu_percent')}%\n"
                    f"RAM: {ram.get('used_gb')}/{ram.get('total_gb')} GB ({ram.get('percent')}%)\n"
                    + "\n".join(gpu_lines)
                    + f"\nDisk I/O: R {disk.get('read_mb', 0):.1f} MB ({disk.get('read_count', 0)} ops) / W {disk.get('write_mb', 0):.1f} MB ({disk.get('write_count', 0)} ops)\n"
                    f"Network I/O: Sent {net.get('sent_mb', 0):.1f} MB ({net.get('packets_sent', 0)} pkts) / Recv {net.get('recv_mb', 0):.1f} MB ({net.get('packets_recv', 0)} pkts)\n"
                    f"Errors: in={net.get('errin', 0)} out={net.get('errout', 0)}\n"
                    f"Process: CPU {proc.get('cpu_percent', '?')}% · Mem {proc.get('mem_mb', '?')} MB · Threads {proc.get('threads', '?')} · FDs {proc.get('fds', '?')}\n\n"
                    f"Usage: {format_status_line()}"
                )
            )
        alerts = s.get("alerts") or []
        alert_lbl.configure(
            text="\n".join(f"⚠ {a}" for a in alerts) if alerts else ("Nothing wrong right now" if simple else "No alerts")
        )

        jobs_box.delete("1.0", "end")
        for j in s.get("train_jobs") or []:
            if simple:
                jobs_box.insert(
                    "end",
                    f"[{j.get('status')}] {j.get('name')} · "
                    f"{int(float(j.get('progress') or 0)*100)}% done\n",
                )
            else:
                jobs_box.insert(
                    "end",
                    f"[{j.get('status')}] {j.get('name')} · "
                    f"{int(float(j.get('progress') or 0)*100)}%\n"
                    f"  loss tail: {str((j.get('metrics') or {}).get('loss') or [])[-5:]}\n",
                )
        if not (s.get("train_jobs") or []):
            jobs_box.insert(
                "end",
                MONITOR_NO_JOBS + "\n" if simple else "No train jobs yet — open Models → Train lab\n",
            )

        log_box.delete("1.0", "end")
        for ev in s.get("recent_events") or []:
            if simple:
                log_box.insert(
                    "end",
                    f"{str(ev.get('at') or '')[11:19]}  "
                    f"{ev.get('message')}\n",
                )
            else:
                log_box.insert(
                    "end",
                    f"{str(ev.get('at') or '')[11:19]}  "
                    f"[{ev.get('level')}] {ev.get('kind')}/{ev.get('source')}: "
                    f"{ev.get('message')}\n",
                )
        if not (s.get("recent_events") or []):
            log_box.insert(
                "end",
                MONITOR_NO_EVENTS + "\n" if simple else "No events yet — use Chat, Team, or Models to generate activity.\n",
            )

        try:
            from app.core.services.system.ops_monitor import log_event

            log_event("monitor", "Activity page refreshed", source="monitor", level="info")
        except Exception:  # noqa: BLE001
            pass

    paint()

    # Fast KPI-only refresh (every 1.5s) + full paint (every 4s)
    def refresh_kpi() -> None:
        """Update only the top KPI strip - lightweight, frequent."""
        try:
            if not (app.winfo_exists() and getattr(app, "_current_page", "") == "Monitor"):
                return
            s = ops.mission_summary()
            hw = s.get("hardware") or {}
            ram = hw.get("ram") or {}
            gpu = (hw.get("gpu") or [{}])[0] if hw.get("gpu") else {}
            disk = hw.get("disk") or {}
            net = hw.get("net") or {}

            # Update only KPI labels (first 6: tokens, cost, CPU, RAM, GPU, Disk, Net, profiles)
            u = s.get("usage") or {}
            tot = (u.get("totals") or {}) if isinstance(u, dict) else {}

            if simple:
                bits = [
                    f"Words used ~{int(tot.get('total_tokens') or 0):,}",
                    f"Est. cost ${float(tot.get('est_cost_usd') or 0):.3f}",
                    f"Computer busy {hw.get('cpu_percent') if hw.get('cpu_percent') is not None else '?'}%",
                    f"RAM {ram.get('used_gb', 0):.1f}/{ram.get('total_gb', 0):.1f} GB ({ram.get('percent', '?')}%)",
                    f"Graphics {gpu.get('util_percent', '—')}%",
                    f"Disk R/W {disk.get('read_mb', 0):.1f}/{disk.get('write_mb', 0):.1f} MB",
                    f"Net S/R {net.get('sent_mb', 0):.1f}/{net.get('recv_mb', 0):.1f} MB",
                    f"Saved AIs {s.get('model_profiles')} · Goals {s.get('team_channels')}",
                ]
            else:
                bits = [
                    f"Tokens {int(tot.get('total_tokens') or 0):,}",
                    f"Est ${float(tot.get('est_cost_usd') or 0):.3f}",
                    f"CPU {hw.get('cpu_percent') if hw.get('cpu_percent') is not None else '?'}%",
                    f"RAM {ram.get('used_gb', 0):.1f}/{ram.get('total_gb', 0):.1f} GB ({ram.get('percent', '?')}%)",
                    f"GPU {gpu.get('util_percent', '—')}%",
                    f"Disk R/W {disk.get('read_mb', 0):.1f}/{disk.get('write_mb', 0):.1f} MB",
                    f"Net S/R {net.get('sent_mb', 0):.1f}/{net.get('recv_mb', 0):.1f} MB",
                    f"Profiles {s.get('model_profiles')} · Team {s.get('team_channels')}",
                ]
            for lb, t in zip(kpi_labels, bits):
                try:
                    lb.configure(text=t)
                except Exception:
                    pass
        except Exception:
            pass
        finally:
            # Always reschedule
            try:
                if app.winfo_exists():
                    app.after(1500, refresh_kpi)
            except Exception:
                pass

    def loop() -> None:
        """Full page repaint - less frequent."""
        try:
            if not (app.winfo_exists() and getattr(app, "_current_page", "") == "Monitor"):
                return
            paint()
        except Exception:
            pass
        finally:
            # Always reschedule
            try:
                if app.winfo_exists():
                    app.after(4000, loop)
            except Exception:
                pass

    # Start both loops
    try:
        app.after(1500, refresh_kpi)
        app.after(4000, loop)
    except Exception:
        pass
