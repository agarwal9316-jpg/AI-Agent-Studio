# Optional icons / branding pack

**Since:** 1.28.2  
**Folder:** `assets/branding/` (next to `Launch.bat` / app root)

Studio ships a small **original** indigo “A” mark (generated with Pillow — no third-party logos).  
Everything is **optional**: if files are missing, the UI soft-degrades (no crash; text-only About/Home; default OS window icon).

---

## What the pack drives

| Asset | Used for |
|-------|----------|
| `app_icon_256.png` / `64` / `32` | Window icon (`iconphoto`), About logo, Home brand mark |
| `app_icon.ico` | Windows taskbar / PyInstaller `EXE(icon=…)` |
| `tray_icon.png` | System tray (falls back to `assets/tray_icon.png`) |
| `logo.svg` | Source / docs / external sites (not required at runtime) |

Loader: `app.core.services.system.branding`  
Settings → **Appearance** shows **Brand accent** (sidebar strip colour from `UI["brand_bar"]`) plus pack ON/optional status.

---

## Replace with your own icons

1. Create or edit files under `assets/branding/` using the **exact names** above.
2. Prefer square PNGs with transparency (RGBA). Recommended sizes: **256**, **64**, **32** (16 optional for tray/favicon).
3. Rebuild the Windows `.ico` (multi-size) either:
   - Run: `python scripts/generate_branding_assets.py --force` after placing a master 256 PNG and adjusting the script, **or**
   - Export `app_icon.ico` from your design tool (include 256/64/32/16).
4. Restart the app (or rebuild the portable EXE) so the window/tray pick up new files.
5. For portable builds, keep `assets/branding/` next to the EXE; the PyInstaller spec already bundles this folder and sets `icon=assets/branding/app_icon.ico`.

### Regenerate the default pack

```bash
python scripts/generate_branding_assets.py --force
```

Requires **Pillow** (`requirements.txt`). Safe to re-run; `--force` overwrites generated files.

---

## Soft-degrade rules

- Missing folder or PNGs → `pack_present()` is false; no window icon / logos applied.
- Corrupt image → loader catches errors and skips that surface.
- Tray prefers `assets/branding/tray_icon.png`, then legacy `assets/tray_icon.png`, then a drawn fallback “A”.

---

## Related

- Roadmap item: Optional icons / branding pack  
- Themes / brand bar colour: `app/ui/themes.py` (`brand_bar`)  
- Tray: `app/core/services/system/system_tray.py`  
