# UX Plan — User-friendly GUI with full feature accessibility

**App version studied:** 1.9.6  
**Date:** 2026-07-25  
**Goal:** Any new user can discover, understand, and use **every shipped feature** without reading external docs or guessing.

---

## 1. Current GUI — what exists today

### 1.1 Shell

| Element | State | Notes |
|---------|--------|--------|
| Sidebar hubs | CHAT / WORK / LIBRARY / SYSTEM | Collapsible; ~20 destinations |
| Brand + Focus + Help + Ctrl+K | Footer actions | Good entry points |
| Status bar | Tips + Ready line | Page tips fire on `show_page` |
| Toasts | Approvals, search, some actions | Not used consistently |
| Contrast | High-contrast tokens (1.9.5) | Mostly fixed |
| Focus mode | Ctrl+\\ | Advanced; not explained in-flow enough |

### 1.2 Navigation map (actual)

```
CHAT:     Home · Help · Chat · Chats · Knowledge · Track
WORK:     Work · Company · CEO · Approvals · Schedule · Org chart · Patches
LIBRARY:  Agents · Tasks · Runs · Projects · Memory
SYSTEM:   Usage · Settings · About
```

**Problem:** ~20 peer pages. Related concepts (Company/CEO/Work/Schedule/Org/Approvals) are split. Casual users never find Track, Memory, Patches, Schedule.

### 1.3 Chat (primary surface)

| Zone | Features accessible |
|------|---------------------|
| Tabs | Multi-chat |
| Title | Rename |
| Mode / Tasks chips | Plan-Action, company approval |
| Caps popover | Terminal, Skills, MCP, Laptop, Workflow, Safety, tool approval, show tools, Agent |
| Provider / Model | LLM selection, search, fetch |
| Comfort | Density toggle |
| Live | Activity + Agents timeline |
| 🔍 / ⋯ | Search chats; overflow (export, params, media tools, marketplace…) |
| + menu | Attach, image, search, OCR, palette |
| Mic / continuous voice | STT |
| Send / Stop | Generation control |
| Coach bar | Dismissible tips |
| Empty state | Steps + starters |
| Bubbles | Markdown, media, copy/edit/reply/regen, tool traces |
| History | Virtualized load-older |

**Strength:** Power is there.  
**Weakness:** Power is **layered** (chips → Caps → ⋯ → dialogs). Users don’t know what exists behind ⋯ or Caps.

### 1.4 Onboarding / teaching already built

| Mechanism | Coverage |
|-----------|----------|
| Setup wizard (4 steps) | Key + Chat basics |
| Home checklist | 6 steps with Go → |
| Help (F2) | Sections + shortcuts |
| Chat coach | 3 lines until dismiss |
| Empty chat | Steps + starters |
| Page status tips | One-liner per page |
| docs/ | Blueprint (developers, not end users) |

### 1.5 Feature accessibility matrix (honest)

| Feature area | Accessible from GUI? | Discoverable by new user? | Gap |
|--------------|----------------------|---------------------------|-----|
| Chat send / stream / stop | Yes | Yes | — |
| Plan / Action | Yes (chip) | Medium | Name “Mode” unclear |
| Terminal / Skills / MCP / Laptop | Caps | Low | Hidden in popover |
| Web search | ⋯ / + / intent | Medium | Easy to miss |
| Image gen | Ctrl+G / + / ⋯ | Medium | Not on main bar |
| OCR | + / ⋯ | Low | Buried |
| Browser tool | Via LLM blocks only | Very low | No “Browse…” UI |
| Knowledge RAG | Knowledge page | Medium | Not linked from empty chat enough |
| Attachments | 📎 | Yes | Drag-drop not obvious |
| Voice | 🎤 🎙 | Medium | Icons only |
| Multi-chat / pin / branch | Tabs + ⋯ | Medium | Branch only in overflow |
| Model params / context | ⋯ Params | Low | Advanced buried |
| Skills manager / marketplace | ⋯ | Very low | Power users only |
| System prompt edit | ⋯ | Low | Critical for power users |
| Tool approval | Caps / Settings / Approvals | Medium | Three places, no single story |
| Company / CEO / Work / Schedule | Separate pages | Low | No “company story” flow |
| Org chart / workflow | Org chart | Low | Duplicate naming (Workflow) |
| Agents / Tasks / Runs | LIBRARY | Medium | Unclear vs Chat agents |
| Memory / Projects | LIBRARY | Low | Why they matter not explained |
| Patches / self-improve | Patches | Low | No path from Chat when patch queued |
| Usage / budgets | Usage | Low | No chip in Chat |
| Themes / density / scale | Settings | Medium | OK |
| Portable Launch / browsers | Launch.bat | Outside GUI | Mention in Help only |
| Track page | Track | Very low | Unclear purpose vs Live |

---

## 2. User problems (from studying current GUI)

### P1 — Too many destinations
Twenty sidebar items force scanning. Hubs help but **LIBRARY/SYSTEM stay collapsed** by default → Agents, Memory, Usage feel “missing.”

### P2 — Features ≠ labeled UI actions
Many capabilities only exist as **LLM tool blocks** (`<<<BROWSER>>>`, `<<<TERMINAL>>>`). Users think “the app can’t browse” because there is no Browse button.

### P3 — Dual mental models
- **Chat agent** (persona + tools) vs **Company agents** (CEO/PM/Engineer)  
- **Runs** (task pipeline) vs **Chat send** vs **Work board tasks**  
Users don’t know which path to use for “get something done.”

### P4 — Progressive disclosure without breadcrumbs
Caps, ⋯, Comfort, Live, Help all hide depth. After dismiss coach, **no persistent “?” on each control**.

### P5 — Success is invisible
Approvals badge exists; patch queue, knowledge index health, schedule next-run, usage budget are not surface-level on Chat.

### P6 — Teaching is front-loaded
Wizard + coach fire early; later pages (Patches, Schedule, Org) still feel like admin tools with little guided copy.

### P7 — Accessibility of actions vs docs
docs/ is excellent for developers; **end-user path is GUI-only**. Help is good but not linked from every high-power dialog (Params, Marketplace, Skills).

---

## 3. Design principles for the redesign plan

1. **One primary job:** Chat to get work done; everything else supports Chat or Company.  
2. **Three user modes:** Beginner · Builder · Operator (company). UI defaults to Beginner, unlocks layers.  
3. **Every feature has a named UI entry** (button, menu item, or Help deep-link)—not only LLM syntax.  
4. **See it → do it → understand result** (empty state → action → toast/badge/Live).  
5. **Never hide critical safety** (Stop, Approvals, Mode) behind ⋯.  
6. **Reduce destinations** by grouping, not by deleting features.  
7. **Same language everywhere** (Mode Action, Caps, Work, Patches).  
8. **Keyboard optional** (palette helps power users; mouse path always exists).

---

## 4. Target information architecture

### 4.1 Simplified nav (recommended)

```
PRIMARY (always expanded)
  Home
  Chat
  Help

WORKSPACE (company + ops)
  Work          ← board (default company view)
  Approvals     ← badge
  Knowledge

MORE ▾ (drawer or hub)
  Agents · Tasks · Runs
  Memory · Projects
  Company · CEO · Org chart · Schedule
  Patches · Track · Chats
  Usage · Settings · About
```

**Rules:**
- Beginner never needs MORE for day-1 success.  
- Badges: Approvals, Patches (pending count), Work (running).  
- “Org chart” rename label to **Org / Workflow** (one name).

### 4.2 Chat as command center (recommended chrome)

```
[Tabs…] [Title] [Mode] [Caps] [Model▾] [Live] [?] [⋯]
[Coach or compact tip strip — optional]
[Messages — center column]
[+ Attach | 🔍 Search | 🖼 Image | 🎤]  [ input ]  [Send] [Stop]
[status: mode · caps · model · usage · tips]
```

Move **high-value actions out of ⋯** onto composer **+** or a second icon row: Search, Image, OCR, Browse (new).

Keep advanced in ⋯: Params, System prompt, Marketplace, Skills manager, Export, Branch, Cwd.

### 4.3 Feature → UI entry (target complete map)

| Feature | Primary UI entry | Secondary |
|---------|------------------|-----------|
| Chat | Chat | Ctrl+K |
| Plan/Action | Mode chip | /plan /action |
| Caps tools | Caps | Comfort bar |
| Web search | Composer 🔍 | ⋯ · slash |
| Image gen | Composer 🖼 | Ctrl+G |
| OCR | Composer + menu | ⋯ |
| **Browse URL** | **New: Browse… dialog** | LLM BROWSER |
| Terminal cwd | Caps → Cwd… | ⋯ |
| Attach | 📎 | drag-drop overlay hint |
| Voice | 🎤 🎙 with labels on first use | Ctrl+M |
| Live tools | Live | Track page |
| Approvals | Sidebar badge | toast |
| Patches | Badge + toast when queued | Patches page |
| Knowledge | Knowledge + empty-chat link | Help |
| Memory | Projects/Memory under MORE + Help | Chat inject silent |
| Company goal | CEO + “Promote chat to goal” | Work |
| Schedule | Schedule under WORKSPACE More | Help |
| Agents/Tasks/Runs | MORE · Library | Help “classic pipeline” |
| Usage | Chip on Chat status | Usage page |
| Settings | SYSTEM | Wizard |
| Help | F2 · ? | Every empty state |

---

## 5. Detailed plan by workstream

### Workstream A — Discoverability & IA (highest impact)

| ID | Task | Acceptance criteria |
|----|------|---------------------|
| A1 | Collapse nav to Primary + Workspace + More | Beginner path ≤ 5 visible items |
| A2 | Pending badges: Approvals, Patches, Work running | Counts update live |
| A3 | Feature directory page (or Help section) listing **every** feature → Open | Full FEATURES inventory linked |
| A4 | Rename/merge confusing labels (Org chart vs Workflow) | One term in UI |
| A5 | Track page: explain vs Live or merge into Live help | User understands purpose |

### Workstream B — Chat command center

| ID | Task | Acceptance criteria |
|----|------|---------------------|
| B1 | Persistent icon row: Attach, Search, Image, OCR, Browse | No need for ⋯ for these |
| B2 | Caps popover: short description under each switch | “Terminal: run shell commands” |
| B3 | Mode chip tooltip/help: Plan vs Action example | One-click “What’s this?” |
| B4 | After tool queue (patch/search/image): toast + optional inline card with next step | “Patch queued → Open Patches” |
| B5 | Usage chip on status or top bar | Tokens/session visible |
| B6 | Drag-drop highlight on composer | “Drop files to attach” |
| B7 | First-time labels under 🎤 🎙 | “Mic” “Talk” text or coach |

### Workstream C — Guided journeys (not only one wizard)

| ID | Task | Acceptance criteria |
|----|------|---------------------|
| C1 | Journey: First chat success | Wizard → Chat starter → first reply celebration |
| C2 | Journey: Web research | Empty state chip → search results card → “Open in browser” |
| C3 | Journey: Knowledge Q&A | Index 1 file → ask → citation visible |
| C4 | Journey: Company goal | CEO create → Work board updates → Approvals if manual |
| C5 | Journey: Safe code change | Ask self-improve → Patches → Apply |  
| C6 | Optional interactive tour (spotlight 5 hotspots on Chat) | Skip anytime; once per install |

### Workstream D — Page-level friendliness

| ID | Task | Acceptance criteria |
|----|------|---------------------|
| D1 | Every page: header + 1-sentence purpose + primary CTA | Already partial; finish Chats/Memory/Projects/Company |
| D2 | Empty states for every list page | “No X yet — [Create]” |
| D3 | Settings: wizard-like sections (Account · Model · Safety · Appearance) | Scan in &lt;10s |
| D4 | Approvals: plain-language “Why blocked” | Tool name + risk line |
| D5 | Knowledge: “How Chat uses this” panel | Links to Chat |
| D6 | Work/CEO/Company: single “Company guide” blurb shared | Consistent story |

### Workstream E — Feedback & confidence

| ID | Task | Acceptance criteria |
|----|------|---------------------|
| E1 | Global toast policy (success/error/next-step) | Consistent |
| E2 | First successful tool run: “Tools worked — see Live” | Educates Live |
| E3 | Unverified claims already exist — surface in UI as yellow callout card | More visible than system_note alone |
| E4 | Connectivity: Settings “Test internet / search” | Uses existing connectivity_check |
| E5 | Health strip on Home (key, search, knowledge, approvals) | At-a-glance |

### Workstream F — Accessibility & clarity

| ID | Task | Acceptance criteria |
|----|------|---------------------|
| F1 | Visible text on icon-only controls (or tooltips on hover) | Mic, Talk, Search, Overflow |
| F2 | Minimum hit target 28–32px (mostly done) | Touch-friendly |
| F3 | Don’t rely on color alone for badges | Count + text |
| F4 | Keyboard: document F2/Ctrl+K in coach forever (compact) | Remains after dismiss |
| F5 | Contrast regression test stays green | `tests/test_contrast_audit.py` |

### Workstream G — Docs alignment (end-user)

| ID | Task | Acceptance criteria |
|----|------|---------------------|
| G1 | `docs/USER_GUIDE.md` generated from `user_guide.py` | Single source |
| G2 | Help page “Feature directory” auto from FEATURES | No stale list |
| G3 | Update UI_MAP to 1.9.6+ IA | Accurate |

---

## 6. Phased delivery (recommended)

### Phase 0 — Plan freeze (this document)
- Stakeholder agrees IA (Primary / Workspace / More).  
- No feature deletion; only regroup + expose.

### Phase 1 — “I can find everything” — **DONE in v1.10.0**
**A1–A3, B1, B4, D1–D2, E1, F1**

Outcome: Search/Image/OCR/Browse on Chat; badges; feature directory; empty states; tooltips/labels.

### Phase 2 — “I understand the story” — **DONE in v1.10.0 (core)**
**B2–B3, B5, D3, E4–E5** (journeys C1–C5 still optional polish)

Outcome: Caps descriptions; Mode help; Settings sections; Test search; health strip; usage on status.

### Phase 3 — “I feel guided” (optional polish)
**C6 tour, A4–A5 rename/merge, B6–B7, G1–G3**

Outcome: Optional spotlight tour; cleaner naming; docs sync.

### Phase 4 — Measure
- First-session checklist completion rate (local flags).  
- % users who open Approvals/Patches after a queue event.  
- Support questions: “where is X?” should drop.

---

## 7. Explicit non-goals (for this UX program)

- Rewriting to web/React only for friendliness.  
- Removing power features to “simplify.”  
- Forcing company workflow for simple chat users.  
- Replacing LLM tool protocol with GUI-only (GUI **plus** tools).

---

## 8. Success criteria (definition of done)

A new user, after install, without external docs, can within **15 minutes**:

1. Add API key  
2. Send a chat message and get a reply  
3. Run a web search from the UI  
4. Attach a file  
5. Index one document and ask about it  
6. Find Approvals and understand a pending item  
7. Find Help and locate any advanced feature (Marketplace, Params, Schedule) via Feature directory  

Power users still reach everything in ≤2 clicks from Chat (icon row or Ctrl+K).

---

## 9. Implementation notes (for later execute)

| Area | Primary files |
|------|----------------|
| IA / nav | `app/ui/app_window.py` `_nav_hubs`, `NAV_ITEMS` |
| Chat chrome | `_page_chat`, overflow, + menu |
| Help / guide | `app/services/user_guide.py`, `_page_help` |
| Badges | `_approval_badge_count` → generalize |
| Browse UI | new dialog + `browser_tool` |
| Journeys | flags in `config.json` + empty states |
| Tests | extend `tests/test_user_friendly.py` |

---

## 10. Summary

**Today:** Feature-rich, partly taught (Help/Home/coach), but **feature surface &gt;&gt; visible controls**, and **company vs chat** stories compete.

**Plan:** Keep power; fix **information architecture**, put **high-value actions on Chat**, give **every feature a named entry + Help link**, add **badges/toasts for outcomes**, and **guided journeys** for the five main jobs (chat, search, knowledge, company, patches).

**Next step after approval:** Implement **Phase 1** (IA + Chat icon row + Feature directory + empty states + labels).
