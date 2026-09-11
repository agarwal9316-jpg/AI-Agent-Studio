# Launch guide

---

## Development (required daily path)

1. Open project folder `AI-Agent-Studio`.  
2. **Double-click `Launch.bat`.**  
3. Window title: **AI Agent Studio**.

First time only:

```bat
cd /d "…\AI-Agent-Studio"
py -3 -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
Launch.bat
```

### What Launch.bat does

1. Uses `.venv\Scripts\python.exe` (space-safe paths).  
2. May run **native ensure** (Playwright Chromium → `./browsers`) if missing.  
3. Starts `python -m app`.  
4. On failure, may write `data\last_launch_error.txt`.

---

## Portable (no Python on target PC)

Build on a machine with Python:

```powershell
cd "…\AI-Agent-Studio"
.\build_portable.ps1
```

Run:

- `Launch_Portable.bat`, or  
- `dist\AI-Agent-Studio\AI-Agent-Studio.exe`

Distribute: zip **`dist\AI-Agent-Studio\`** entire folder.  
Data is created as `data\` next to the exe.

---

## Prerequisites

| Mode | Need |
|------|------|
| Dev | Windows 10/11, Python 3.11+, `.venv` |
| Portable | Windows only |
| LLM features | OpenAI-compatible key in Settings |
| Image gen | Key + provider that supports `/images/generations` |
| Browser tool | First Launch native setup (or pre-copied `browsers/`) |

---

## Manual dev start (debug)

```bat
.\.venv\Scripts\python.exe -m app
```
