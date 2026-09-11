# Self-improve (safe)

The assistant can modify **app source** when in **Action** mode by emitting blocks. The host creates a backup first; invalid Python is restored.

---

## Allowed paths

- `app/**`  
- `docs/**` (keep documentation in sync when changing behavior)  
- Root: `requirements.txt`, `README.md`, `FEATURES.md`, `Launch.bat`, `Launch.ps1`

**Forbidden:** `data/`, `.venv/`, `__pycache__`, `.git/`, paths outside app root.

---

## Blocks

### Backup only

```
<<<BACKUP>>>
reason: before change
<<<END_BACKUP>>>
```

### Apply file write

```
<<<SELF_IMPROVE>>>
path: app/services/example.py
mode: write
note: short description
---
# full new file content
<<<END_SELF_IMPROVE>>>
```

### Rollback

```
<<<ROLLBACK>>>
backup_YYYYMMDD_HHMMSS
<<<END_ROLLBACK>>>
```

Empty id → latest backup.

### Safer alternative: patch review

```
<<<PATCH_REVIEW>>>
…
<<<END_PATCH_REVIEW>>>
```

User applies on **Patches** page.

---

## After UI changes

Restart via **Launch.bat** so Python reloads UI modules.

---

## Implementation

- `app/services/self_improve.py`  
- Invoked from `chat.py` → `run_self_improve_from_reply`  
- Backups: `data/backups/self_improve/`  
