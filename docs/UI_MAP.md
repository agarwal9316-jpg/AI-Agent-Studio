# UI Map

**Toolkit:** CustomTkinter  
**Version:** 1.27.94 (keep in sync with `app/version.py`)

---

## 1. Global chrome

| Element | Description |
|---------|-------------|
| Title | AI Agent Studio + version (`self.title`) |
| Window controls | **OS title bar only** (min / max / close) — no second in-app — □ ✕ strip |
| Sidebar | Scrollable nav (`CTkScrollableFrame`) |
| Content | Swaps page for selected nav item |
| Status bar | Short status / path / busy / version |

### Sidebar pages (typical order)

Chat · Home · Agents · Tasks · Runs · Chats · Memory · Projects · Company · CEO · Workflow · Knowledge · Notes · Channels · Automations · Approvals · Patches · Schedule · Usage · Settings · About  

*(Exact labels come from `app_window` nav construction.)*

---

## 2. Chat page (primary)

### Row 0 — Top bar

| Control | Role |
|---------|------|
| Chat tabs | Multi-chat open tabs (+ / ×) |
| Title button | Rename chat |
| Live | Toggle Live activity panel |
| 🔍 | Search this/all chats |
| ⋯ | Overflow menu (full tools) |

### Row 1 — Provider / model

| Control | Role |
|---------|------|
| Provider | OpenAI, OpenRouter, … |
| Model | Active model |
| Search models | Filter list |
| Find | Model picker dialog |
| ↻ models | Refresh from API |

### Row 2 — Mode · approvals · capabilities

| Control | Role |
|---------|------|
| Mode plan \| action | Tool execution off/on |
| Tasks manual \| auto | Company approval mode |
| Tool approval | Risky tools → Approvals queue |
| Terminal / Skills / MCP / Laptop / Workflow / Safety | Per-chat flags |
| Agent… | Persona picker |
| More… | Same as ⋯ |

### Row 3 — Messages

- Scrollable transcript (Grok-like bubbles)
- Optional **Live** side panel: Activity \| Agents
- Streaming updates in-place (less flicker)
- Message actions: Copy / Edit / Reply / Regen
- Media: images/videos from IMAGE blocks / gen / screenshots

### Row 4 — Composer

| Control | Role |
|---------|------|
| 📎 | Attach files |
| 🎤 | Mic STT |
| 🎙 | Continuous voice |
| Textbox | Input (Enter send, Ctrl+Enter) |
| Send | Start generation · while busy **queues** follow-up (P1.4) |
| Stop | Cancel loop |
| Status line | mode · tasks · tool-appr · caps · attaches |

### Contrast

Chrome colors from `app/services/themes.py` → `UI` + `style_*` helpers (forced high contrast).

---

## 3. Other key screens

| Page | Purpose |
|------|---------|
| **Home** | Welcome / quick links / last run |
| **Agents** | CRUD agents |
| **Tasks** | CRUD tasks |
| **Runs** | Mock or LLM multi-task runs |
| **Chats** | Manage chat list |
| **Memory** | Long-term facts |
| **Projects** | Project scope |
| **Company** | Roles / work queue |
| **CEO** | Goals, Run plan, approval mode, pending |
| **Organisation / Workflow** | Visual org chart (see §3a) |
| **Team** | Teams-style channels + org pipeline runs |
| **Knowledge** | Index files/folders, watch, search |
| **Approvals** | Tool + company pending |
| **Patches** | Review/apply/reject SELF_IMPROVE-style patches |
| **Schedule** | Timed jobs → company queue |
| **Usage** | Token/budget meter |
| **Settings** | Theme, API, stream, image model, tool approval |
| **About** | Version, not-a-clone notice |

### 3a. Organisation chart page (`org_page` + `org_chart_view`)

**Layout:** `[ toolbar + visual chart | collapsible right panel ]`

| Zone | Controls |
|------|----------|
| Top toolbar | Chart switcher · New org · **✨ AI create** · Rename · Copy · Export · Import · Delete |
| Chart actions | + Add AI Worker · Search workers |
| Chart canvas | CEO top · branch columns · continuous connectors · card + / ▾ |
| Chart view tools | Expand all · Collapse all · 🖐 Drag view · wheel/pan · **Reset · CEO top + collapse teams** |
| Right: **All organisations** | List every chart (Test SWAT, Beta Org, …) · ☑ Select all · Open / Rename / Copy / New / Delete |
| Right: **Workers in this org** | Full tree list · ☑ bulk · + per row · × remove |
| Right: **Selection details** | Title, order, instructions, role, goal, quick LLM · Save / Config / Inspect / Remove |
| Right: **Tree preview** | ASCII pipeline preview (collapsible) |
| Card ▾ menu | Add child · Configure · Goal · Assignments · Execution · Reports · Comms · Duplicate · Move · Enable/Disable · Remove |

**✨ AI create dialog:** **LLM** (Provider · Base URL · API key · Model · **💾 Save LLM settings** · ↻ models) · kind · requirements · size/custom seats · **footer status + progress bar** while creating · log `data/logs/org_ai.log` · prompts filled per seat.

---

## 4. Dialogs (Chat)

- Overflow menu (rename, pin, branch, export, params, capabilities, media)
- Model picker / params
- Image gen, OCR, web search
- System prompt editor
- Skills manager / marketplace
- Agent picker

---

## 5. Keyboard shortcuts (common)

| Shortcut | Action |
|----------|--------|
| Enter | Send (chat) |
| Ctrl+Enter | Send |
| Ctrl+M | Mic |
| Ctrl+G | Image gen dialog |
| F1 | Shortcuts help |

---

## 6. Theme

Settings → theme names from `themes.THEMES` (Readable Dark/Light recommended).  
Chat chrome always uses explicit `UI` colors so text stays readable.


---

## Notes page (1.27.90)

| Control | Role |
|---------|------|
| Search | Filter title/body |
| New / list | Create + select notes |
| Title + body | Markdown/plain editor |
| Save / Delete | Persist under `data/notes/` |
| Attach to chat | Chip on Chat composer → full-context inject next send |
| AI rewrite | Optional LLM rewrite of selection (soft-degrade if no key) |



## Channels page (1.27.91)

| Control | Role |
|---------|------|
| Channel list | Search / New / Rename / Delete |
| Timeline | User + model + system messages |
| Post | User message (works without API key) |
| Ask model | Picker or `@model` mention → model reply into channel |
| Soft pin | Pin/unpin messages shown above timeline |
| Reply | Soft thread (`parent_id` / `reply_to`) |

Separate from **Team** goal channels (`data/team_channels/`).


## Chat message queue (1.27.93)

| Control | Role |
|---------|------|
| Send while busy | Enqueue follow-up (FIFO) instead of blocking |
| Queue chips | Under composer — preview + × remove |
| Clear queue | Drop all queued follow-ups |
| Auto-send | On turn idle, dequeue next and send |
| Stop | Cancels active run; **keeps** queue (clear explicitly) |

## Voice settings (1.27.94 / P2.1)

Settings → **Voice**: mic/TTS toggles, mic mode (push_to_talk / toggle), language,
**STT engine** (`local` | `openai_whisper`), **TTS engine** (`local` | `openai` | `elevenlabs`),
TTS voice, optional ElevenLabs API key, **Test STT** / **Test TTS**.
Chat composer 🎤 / 🔊 and auto-read-aloud use the selected engines; soft-degrade to local.

## Automations page (1.27.92)

| Control | Role |
|---------|------|
| Search / New / list | Find + create automations |
| Name + prompt | What to send each run |
| Schedule | Hourly · Daily · Weekdays · Every N minutes (+ hour/min) |
| Save / Enable/Disable / Delete | Persist under `data/automations.json` |
| Run now | Fire immediately → linked result chat |
| Open last chat | Jump to Chat for `last_chat_id` |

Background ticker (daemon thread) fires due jobs while the app runs. Separate from Company **Schedule**.

