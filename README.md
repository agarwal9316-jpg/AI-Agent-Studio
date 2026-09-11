# AI Agent Studio

Portable **Windows GUI** for multi-agent chat, company workflows, tools, and local knowledge.

Inspired by AutoGen / CrewAI / Dify / Langflow for **patterns only** — original software, **not a clone**.

**Version:** 1.27.80 (see `app/version.py` · [docs/CHANGELOG.md](docs/CHANGELOG.md)) · [GitHub Releases](https://github.com/agarwal9316-jpg/AI-Agent-Studio/releases)  


---

## Quick start (Windows PC)

1. Install [Python 3.11+](https://www.python.org/downloads/) (enable **Add to PATH**).
2. Unzip a release or clone this repo.
3. Double-click **`Start.bat`** (or `Launch.bat`).
   - First run creates `.venv`, installs `requirements.txt`, and installs portable Chromium into `./browsers`.
4. Optional portable EXE: run `build_portable.ps1`, then `Launch_Portable.bat`.

## Android companion

The studio is a **desktop** CustomTkinter app. The Android APK (from Releases) is a companion with update checks (GitHub API + `android/latest-release.json` fallback), release links, and docs — not a full mobile port.


## Documentation (full blueprint)

**All product docs live in [`docs/`](docs/README.md).**

| Start | Link |
|-------|------|
| Doc index | [docs/README.md](docs/README.md) |
| Full blueprint | [docs/BLUEPRINT.md](docs/BLUEPRINT.md) |
| Architecture | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) |
| Features | [docs/FEATURES.md](docs/FEATURES.md) |
| Tools protocol | [docs/TOOLS_PROTOCOL.md](docs/TOOLS_PROTOCOL.md) |
| UI map | [docs/UI_MAP.md](docs/UI_MAP.md) |
| Data model | [docs/DATA_MODEL.md](docs/DATA_MODEL.md) |
| Launch | [docs/LAUNCH.md](docs/LAUNCH.md) |
| Changelog | [docs/CHANGELOG.md](docs/CHANGELOG.md) |
| Resume after months | [docs/CONTINUITY.md](docs/CONTINUITY.md) |

---

## What this is

- Desktop app (Python + CustomTkinter)
- **Start with `Launch.bat`** (development)
- **Portable:** `Launch_Portable.bat` or `dist\AI-Agent-Studio\AI-Agent-Studio.exe`
- State in `.\data` (portable next to app)
- Operator chat: terminal, browser, IMAGE_GEN, RAG, company AI, self-improve

---

## Folder map

```
AI-Agent-Studio/
  docs/                   ← full documentation (maintain here)
  Launch.bat              ← REQUIRED for dev
  Launch.ps1
  Launch_Portable.bat
  README.md               ← this short entry
  FEATURES.md             ← pointer → docs/FEATURES.md
  requirements.txt
  build_portable.ps1
  entry.py
  app/                    ← source
  data/                   ← runtime (created)
  browsers/               ← portable Chromium (Launch setup)
  dist/                   ← portable build output
```

### Absolute paths (this machine)

| Role | Path |
|------|------|
| **This project** | `…\AI Management\Developed Softwares\AI-Agent-Studio` |
| **Docs** | `…\AI-Agent-Studio\docs\` |
| **Parent Checklist** | `…\AI Management\Checklist` (historical process) |
| **Parent Plan** | `…\AI Management\Plan\` |
| **Source (read-only)** | `…\AI Management\Source Code` |

---

## How to launch

1. Double-click **`Launch.bat`**.  
2. First-time: create `.venv` and `pip install -r requirements.txt` (see [docs/LAUNCH.md](docs/LAUNCH.md)).  
3. Portable: `.\build_portable.ps1` then `Launch_Portable.bat`.

---

## Prerequisites

- Windows 10/11  
- Dev: Python 3.11+ and `.venv`  
- Portable: Windows only  
- Optional: OpenAI-compatible API key in **Settings**

---

## Resume here

- **Last version:** **1.27.35** — critical stability fixes (blank white screen, Variable master args, CTkFont root init) · see [docs/CONTINUITY.md](docs/CONTINUITY.md)  
- **Docs pack:** `docs/` is the maintained blueprint  
- **Launch:** **`Launch.bat`** (source; rebuild portable for dist)  
- **Detail:** [docs/CONTINUITY.md](docs/CONTINUITY.md) · [docs/CHANGELOG.md](docs/CHANGELOG.md)

---

## Architecture (summary)

| Piece | Choice |
|-------|--------|
| GUI | CustomTkinter |
| Dev entry | Launch.bat → `.venv\…\python.exe -m app` |
| Data | `./data` |
| LLM | OpenAI-compatible HTTP |
| Packaging | PyInstaller onedir |

Full detail: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

---

## Troubleshooting

See [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md).

Quick: Launch fails → `data\last_launch_error.txt` · missing modules → reinstall requirements · tools noop → Mode = **action**.

---

## Changelog

Full history: [docs/CHANGELOG.md](docs/CHANGELOG.md).

| Version | Notes |
|---------|--------|
| **1.27.35** | **Critical stability:** blank white screen fix (persistent bg frame); all tkinter Variable master args fixed; CTkFont default root window set — eliminates startup/navigation crashes |
| 1.9.0 | Trust pack: capabilities, claims, Stop, restore, Work board, redaction |
| 1.8.0 | GUI sprints: density, hubs, palette, auto image, wizard |
| 1.7.8 | Project `docs/` blueprint pack; root README/FEATURES point to docs |
| 1.7.7 | High-contrast chat chrome |
| 1.7.6 | IMAGE_GEN honesty (no SVG fakes) |
| 1.7.5 | Visible plan/approval/caps bar restored |
| 0.1–1.7 | See docs/CHANGELOG |

---

## License

Original code: **MIT**. Third-party packages keep their own licenses.  
Inspiration / compliance notes: parent Checklist (see [docs/EXTERNAL.md](docs/EXTERNAL.md)).
