"""Chat voice — extracted from AppWindow."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import customtkinter as ctk
import tkinter.messagebox as messagebox

if TYPE_CHECKING:
    from app.ui.app_window import AppWindow


def chat_voice_continuous(app) -> None:
    """Toggle continuous voice conversation (Settings mic mode = toggle)."""
    try:
        from app.core.services.ai import voice_settings as _vs
        from app.core.services.ai.stt_service import (
            continuous_running,
            start_continuous,
            stop_continuous,
            stt_capability,
        )
    except Exception as e:  # noqa: BLE001
        messagebox.showinfo("Voice", f"Mic / STT unavailable: {e}", parent=app)
        return

    if continuous_running():
        stop_continuous()
        app.set_status("Continuous voice OFF")
        try:
            app._voice_refresh_composer_buttons()
        except Exception:  # noqa: BLE001
            pass
        return

    if not _vs.mic_enabled():
        messagebox.showinfo(
            "Voice",
            "Mic input is disabled in Settings → Voice.",
            parent=app,
        )
        return

    cap = stt_capability()
    if not cap.get("available"):
        messagebox.showinfo(
            "Voice",
            (cap.get("detail") or "STT unavailable")
            + ("\n" + (cap.get("hint") or "")).rstrip(),
            parent=app,
        )
        app.set_status(f"STT unavailable: {(cap.get('detail') or '')[:80]}")
        return

    lang = _vs.voice_language()

    def on_utt(result: dict) -> None:
        if result.get("degraded") and not result.get("ok"):
            err = str(result.get("error") or "STT unavailable")

            def err_ui() -> None:
                if not app.winfo_exists():
                    return
                messagebox.showinfo("Voice", err, parent=app)
                app.set_status(f"Voice: {err[:80]}")
                try:
                    app._voice_refresh_composer_buttons()
                except Exception:  # noqa: BLE001
                    pass

            try:
                app.after(0, err_ui)
            except Exception:  # noqa: BLE001
                pass
            return

        text = str(result.get("text") or "").strip()
        if not text:
            return

        def ui() -> None:
            if not app.winfo_exists():
                return
            if hasattr(app, "chat_input"):
                try:
                    if getattr(app, "_composer_is_placeholder", False):
                        app._composer_set_text(text)
                    else:
                        app._composer_set_text(text)
                except Exception:  # noqa: BLE001
                    app.chat_input.delete("1.0", "end")
                    app.chat_input.insert("1.0", text)
            if not app._chat_busy:
                app._chat_send()
            else:
                app._enqueue_composer_followup(text=text, source="voice")

        try:
            app.after(0, ui)
        except Exception:  # noqa: BLE001
            pass

    start_continuous(
        on_utt,
        language=lang,
        on_status=lambda m: app.after(0, lambda: app.set_status(m) if app.winfo_exists() else None),
    )
    app.set_status("Continuous voice ON — speak freely; click 🎤 again to stop")
    try:
        app._voice_refresh_composer_buttons()
    except Exception:  # noqa: BLE001
        pass


def chat_mic(app) -> None:
    """Speech-to-text into the chat input (Ctrl+M). Respects Settings → Voice."""
    try:
        from app.core.services.ai import voice_settings as _vs
        from app.core.services.ai.stt_service import continuous_running, listen_async, stt_capability
    except Exception as e:  # noqa: BLE001
        messagebox.showinfo("Mic / STT", f"Mic unavailable: {e}", parent=app)
        return

    if not _vs.mic_enabled():
        messagebox.showinfo(
            "Mic / STT",
            "Mic input is disabled in Settings → Voice. Enable “Mic input in chat” to use 🎤.",
            parent=app,
        )
        return

    if _vs.mic_mode() == "toggle":
        app._chat_voice_continuous()
        return

    if continuous_running():
        from app.core.services.ai.stt_service import stop_continuous

        stop_continuous()
        app.set_status("Continuous voice OFF")
        try:
            app._voice_refresh_composer_buttons()
        except Exception:  # noqa: BLE001
            pass
        return

    if getattr(app, "_mic_busy", False):
        app.set_status("Mic already listening…")
        return

    cap = stt_capability()
    if not cap.get("available"):
        messagebox.showinfo(
            "Mic / STT",
            (cap.get("detail") or "STT unavailable")
            + ("\n" + (cap.get("hint") or "")).rstrip(),
            parent=app,
        )
        app.set_status(f"Mic unavailable: {(cap.get('detail') or '')[:80]}")
        return

    app._mic_busy = True
    app.set_status("🎤 Listening… speak now")
    if hasattr(app, "chat_status"):
        try:
            app.chat_status.configure(text="Listening…")
        except Exception:  # noqa: BLE001
            pass

    lang = _vs.voice_language()

    def done(result: dict) -> None:
        def ui() -> None:
            app._mic_busy = False
            if not app.winfo_exists():
                return
            if result.get("ok") and result.get("text"):
                text = str(result["text"]).strip()
                if hasattr(app, "chat_input"):
                    if getattr(app, "_composer_is_placeholder", False):
                        app._composer_set_text(text)
                    else:
                        cur = app.chat_input.get("1.0", "end").strip()
                        if cur:
                            app._composer_set_text(" " + text, append=True)
                        else:
                            app._composer_set_text(text)
                app.set_status(f"Mic OK ({result.get('engine')}): {text[:60]}")
                if hasattr(app, "chat_status"):
                    app.chat_status.configure(text="Ready")
            else:
                err = result.get("error") or "No speech"
                hint = result.get("hint") or ""
                msg = err + (f"\n{hint}" if hint else "")
                messagebox.showinfo("Mic / STT", msg, parent=app)
                app.set_status(f"Mic: {err[:80]}")
                if hasattr(app, "chat_status"):
                    app.chat_status.configure(text="Ready")

        try:
            app.after(0, ui)
        except Exception:  # noqa: BLE001
            app._mic_busy = False

    listen_async(
        done,
        language=lang,
        on_status=lambda m: app.after(0, lambda: app.set_status(m) if app.winfo_exists() else None),
    )
