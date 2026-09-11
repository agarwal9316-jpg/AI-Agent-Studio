# Continuity — resume without chat history

**Head:** 1.28.0 — Richer flow canvas (branch `feat/roadmap-flow-canvas`).


**Goal:** After months, open the project folder and continue.

---

## Required files

| File | Purpose |
|------|---------|
| `README.md` (root) | Short entry + Resume + link to docs |
| `docs/**` | Full blueprint & maintenance |
| `Launch.bat` | Double-click start |
| `Launch.ps1` | Shared launch logic |
| `Launch_Portable.bat` | Dist start |
| `requirements.txt` | Dependencies |
| `build_portable.ps1` | Portable build |
| `app/` | Source |
| `app/version.py` | Version stamp |

---

## Resume here (update every release)

- **Last version:** **1.28.0** (Richer flow canvas — Org chart ↔ Flow canvas toggle; nodes/edges pan/zoom/link; persist with workflow store; soft-degrade)
- **Prior:** **1.27.99** (Studio bundle export/import — portable data zip; secrets redacted by default; Settings+About; merge/replace)
- **Prior:** **1.27.98** (Docs sync process — `scripts/check_docs_sync.py` + RELEASE checklist; enforced VERSION trio / CHANGELOG / CONTINUITY / FEATURES)
- **Prior:** **1.27.97** (Virtualized long chat history — sliding window 50/max 200; Load older/newer; soft-degrade; no stream full-rebuild)
- **Prior:** **1.27.96** (Filesystem sandbox profiles — Read-only workspace / Project-only / Full disk with ask; custom roots; file+shell enforce)
- **Prior:** **1.27.95** (P2.2 Artifacts persistent store — Live Artifacts This turn/Saved; `data/artifacts/`; soft-degrade)
- **Recent (1.27.7–1.27.34):**
  - Chat delete reliability + title repair; **OS-only** min/max/close (no duplicate chrome)
  - **Org chart:** pan/drag view, expand/collapse teams, Reset → CEO top; continuous connectors; soft-select (no click flicker)
  - **Org right panel:** All organisations list (☑ bulk open/rename/copy/delete) + workers tree + selection details + **Save** + system/worker prompts
  - **✨ AI create:** kind + requirements + size/**custom seats** + LLM picker + **Save LLM settings** + live status/progress; 240–300s timeout; **data/logs/org_ai.log**
  - **Launch:** 1.27.19 force-show (fixes window gone after flicker); theme still pre-applied
  - **1.27.35 stability:** blank white screen fix on page switch; all Variable master args fixed; CTkFont root window init — no more startup/navigation crashes
- **How users learn the app:** Home checklist · **Help (F2)** · Chat coach bar · Setup wizard  
- **Stage B/C:** Complete  
- **Docs:** `docs/` is the source of truth (full blueprint pack)  
- **Chat UI:** Grok-style rail · ⋯ menus · composer pill · Ctrl+K · slash cmds  
- **Launch:** double-click **`Launch.bat`** (source; do not use stale dist exe for org UI)  
- **Portable:** **`Launch_Portable.bat`** after rebuild  
- **Flow:** Launch → Chat · **Org chart** (Org chart | Flow canvas) · Team · Approvals / Knowledge / CEO as needed  
- **Features:** [FEATURES.md](FEATURES.md) · history [CHANGELOG.md](CHANGELOG.md)  
- **Blueprint:** [BLUEPRINT.md](BLUEPRINT.md)  

---

## Checklist process (parent pack)

Historical/stage checklists still live under parent AI Management (see [EXTERNAL.md](EXTERNAL.md)):

1. Stage B master checklist — complete  
2. Stage C v1.6 checklist — complete  
3. One ID → test → PASS → checkpoint  

New work should still update **docs/CHANGELOG** + **Resume** here.
