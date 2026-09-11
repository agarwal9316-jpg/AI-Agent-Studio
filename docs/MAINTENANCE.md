# Documentation maintenance

## Source of truth

| Topic | File |
|-------|------|
| Version number | `app/version.py` |
| Doc index | `docs/README.md` |
| Product vision | `docs/BLUEPRINT.md` |
| Features table | `docs/FEATURES.md` |
| History | `docs/CHANGELOG.md` |
| Resume blurb | `docs/CONTINUITY.md` + root `README.md` |
| Tool syntax | `docs/TOOLS_PROTOCOL.md` + `capability_manual.py` |
| UI layout | `docs/UI_MAP.md` |
| Data files | `docs/DATA_MODEL.md` |

Root `FEATURES.md` and root `README.md` must **link** here, not diverge long-term.

---

## Enforceable release gate

Every release must pass:

```bat
python scripts/check_docs_sync.py
```

See [RELEASE.md](RELEASE.md) for the short checklist (VERSION trio · CHANGELOG · CONTINUITY/FEATURES · checker).

---

## Checklist when shipping a change

1. Bump `app/version.py` if user-visible.  
2. Add row to `docs/CHANGELOG.md`.  
3. Update `docs/FEATURES.md` if new capability.  
4. Update `docs/TOOLS_PROTOCOL.md` if new `<<<BLOCK>>>`.  
5. Update `docs/UI_MAP.md` if chrome/pages change.  
6. Update `docs/DATA_MODEL.md` if new `data/` files.  
7. Update Resume in `docs/CONTINUITY.md` + root README.  
8. Refresh version line in `docs/README.md` / BLUEPRINT header if needed.  
9. Keep `capability_manual.py` honest (no “YES” without implementation).  

---

## If self-improve edits code

- Prefer also editing matching `docs/` files in the same change (or note “docs TODO”).  
- To allow SELF_IMPROVE on `docs/`, extend `ALLOWED_PREFIXES` in `self_improve.py`.

---

## Review cadence

| When | Action |
|------|--------|
| Each release | CHANGELOG + CONTINUITY Resume |
| Monthly | Skim FEATURES vs Settings/Chat UI for drift |
| After declutter/redesign | UI_MAP + screenshots optional under `data/screenshots` |
