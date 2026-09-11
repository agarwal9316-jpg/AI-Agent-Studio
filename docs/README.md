# AI Agent Studio — Documentation

**Version:** 1.27.37 (see `app/version.py` / `VERSION`)  
**Last updated:** 2026-08-15  
**Home of all project docs.** Prefer editing files here; keep root `README.md` as the short continuity entry.

---

## Start here

| Doc | Purpose |
|-----|---------|
| [BLUEPRINT.md](BLUEPRINT.md) | Full product blueprint (what it is, goals, layers) |
| [ARCHITECTURE.md](ARCHITECTURE.md) | As-built architecture & ADRs |
| [UI_MAP.md](UI_MAP.md) | Screens, chat chrome, navigation |
| [DATA_MODEL.md](DATA_MODEL.md) | `data/` layout, JSON shapes |
| [TOOLS_PROTOCOL.md](TOOLS_PROTOCOL.md) | LLM tool blocks (`<<<…>>>`) |
| [FEATURES.md](FEATURES.md) | Feature inventory (status + where) |
| [CHANGELOG.md](CHANGELOG.md) | Version history |
| [ROADMAP.md](ROADMAP.md) | Done vs next |
| [LAUNCH.md](LAUNCH.md) | Dev + portable launch |
| [TROUBLESHOOTING.md](TROUBLESHOOTING.md) | Common failures |
| [SELF_IMPROVE.md](SELF_IMPROVE.md) | Safe self-modify protocol |
| [CONTINUITY.md](CONTINUITY.md) | Resume after months without chat history |
| [EXTERNAL.md](EXTERNAL.md) | Parent Checklist / Plan / Source Code links |
| [MAINTENANCE.md](MAINTENANCE.md) | How to keep docs accurate |
| [UX_PLAN_USER_FRIENDLY.md](UX_PLAN_USER_FRIENDLY.md) | Plan: discoverable, friendly GUI + full feature access |

---

## Rules

1. **All long-form docs live under `docs/`.**  
2. Root `README.md` = launch + resume pointer only (links here).  
3. Root `FEATURES.md` redirects to `docs/FEATURES.md`.  
4. When shipping a user-visible change: update **FEATURES**, **CHANGELOG**, and **Resume** in CONTINUITY / root README.  
5. When adding a tool block: update **TOOLS_PROTOCOL** and `app/services/capability_manual.py`.  
6. Version source of truth: `app/version.py`.

---

## Folder map (project)

```
AI-Agent-Studio/
  docs/                 ← you are here
  app/                  ← Python package (ui, services, tools)
  data/                 ← runtime portable state (not docs)
  browsers/             ← portable Chromium (Launch setup)
  Launch.bat            ← primary dev entry
  Launch_Portable.bat
  requirements.txt
  README.md             ← short continuity + link to docs/
  FEATURES.md           ← pointer → docs/FEATURES.md
```
