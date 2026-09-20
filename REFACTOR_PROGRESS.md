# AI Agent Studio — ready on main

## User steps (only these)

```text
git clone https://github.com/agarwal9316-jpg/AI-Agent-Studio.git
cd AI-Agent-Studio
Launch.bat
```

That is everything. First launch materializes UI modules and restores any truncated helpers automatically.

## What Launch.bat does for you

1. Creates `.venv` if needed  
2. Runs `ensure_refactor_modules()`  
3. Restores full `task_watch.py` if needed  
4. Decompresses UI payloads into full modules  
5. Starts the app  

No manual install scripts. No payload cleanup. No extra pulls.

## Optional (developers only)

```text
python scripts/smoke_launch.py
```

Headless materialize + compile check — not required to use the app.
