# Feature inventory

**Version:** 1.27.87  
**Maintained here** (root `FEATURES.md` is a pointer).  
**History:** [CHANGELOG.md](CHANGELOG.md) · resume [CONTINUITY.md](CONTINUITY.md)

| Feature | Status | Where |
|---------|--------|--------|
| **AI Organisation chart (visual)** | Yes | Org/Workflow page · `org_chart_view` · CEO top, branch columns, cards |
| Org expand/collapse + pan view + Reset CEO | Yes | Chart toolbar · bottom Reset · free drag / middle-mouse |
| Org right panel: All orgs ☑ + workers tree ☑ + Save | Yes | `org_page` · bulk actions · system/worker prompt fields |
| ✨ AI create (kind · requirements · size/seats · LLM) | Yes | `org_ai` · 240–300s timeout · bg thread · fills prompts |
| Org AI diagnostics log | Yes | `data/logs/org_ai.log` · `app.services.app_log` |
| Worker config: system + worker prompts · LLM inherit | Yes | `org_worker_dialogs` · Default vs override |
| Multi org charts (new/rename/copy/import/export) | Yes | `workflow_graph` · Export strips secrets |
| Chat delete + rail pin/rename/drag | Yes | `chat_store` · history rail ⋯ / right-click |
| Single OS window chrome (no duplicate min/max/✕) | Yes | `app_window` · OS title bar only |
| System tray + run in background | Yes | `system_tray` · Show/Hide/Quit · Settings · 1.27.81 |
| Tool call audit log (export JSON/CSV) | Yes | `audit_log` · Settings · 1.27.82 |
| Offline · Ollama (local) | Yes | Settings/Models · `ollama_local` · health + 11434 · 1.27.83 |
| Voice in/out first-class | Yes | Settings → Voice · 🎤/🔊 · `voice_settings` · soft-degrade · 1.27.84 |
| Native OpenAI tool_calls + role:tool | Yes | Settings toggle · `native_tool_calls` · dual-path · 1.27.86 |
| Multi-model compare / arena | Yes | Chat **Compare** chip · `multimodel` · 2–3 parallel text replies · 1.27.87 |
| Launch always-visible (no stuck hide) | Yes | theme pre-apply · force deiconify · no alpha-0 |
| Browser headless→headed anti-bot fallback | Yes | `browser_tool` · captcha wait |
| Perchance image path (portable Chromium) | Yes | `perchance_image` · may still hit site anti-bot |
| Max context (128k default) | Yes | `model_params` · reserve 8k for reply |
| Rolling chat summary | Yes | `chat_context` · `data/chat_summaries/` |
| Sticky Memory + goal | Yes | Injected every turn after system |
| Auto-memory facts | Yes | Decision lines → Memory page |
| Agent harness (Grok-style) | Yes | `agent_harness/` · file/grep/subagent/git/bg/plan/hooks |
| READ_FILE / WRITE_FILE / SEARCH_REPLACE | Yes | Chat tool blocks |
| LIST_DIR / GREP | Yes | Chat tool blocks |
| Subagents (explore/plan/general) | Yes | SPAWN_SUBAGENT · data/subagents/ |
| Permission allow/ask/deny | Yes | config agent_*_rules · Settings Agent harness |
| Workspace sandbox | Yes | agent_sandbox_enabled · profiles |
| Plan.md mode | Yes | ENTER_PLAN / PLAN_WRITE · data/plans/ |
| AGENTS.md project rules | Yes | Auto inject from cwd walk |
| Lifecycle hooks | Yes | data/hooks/*.json |
| Background shell tasks | Yes | BG_SHELL / BG_STATUS · data/bg_tasks/ |
| Git helpers | Yes | GIT_STATUS / DIFF / COMMIT / … |
| Agent todos | Yes | TODO_WRITE |
| Ask user structured Q | Yes | ASK_USER · pending_questions.json |
| Headless CLI | Yes | `python studio_agent.py -p "…"` |
| GUI shell polish | Yes | Cards home · sidebar icons · brand accent · focus mode · status bar |
| Focus mode | Yes | Ctrl+\\ or sidebar **Focus** · Esc restore |
| Chat avatars + markdown lite | Yes | A/Y circles · headings · bullets · code fences |
| Toasts | Yes | Corner toasts for approvals / search / key events |
| Token meta on bubbles | Yes | prompt→completion tokens when available |
| Consistent page headers | Yes | Work · Approvals · Knowledge · Settings · Agents · … |
| Markdown tables + nested lists | Yes | Chat bubbles |
| Virtualized chat history | Yes | Last 50 items · Load older (+40) · Show all |
| Help / How-to guide | Yes | Sidebar **Help** · F2 · Home checklist |
| Chat coach bar | Yes | Tips until Dismiss · re-enable from Help/Home |
| Empty-chat guide | Yes | Numbered steps + starter chips |
| Page tips in status | Yes | One-line tip when opening each page |
| PRIMARY / WORKSPACE / MORE nav | Yes | Beginner-first IA (More collapsed) |
| Work / Patches badges | Yes | Running tasks · pending patches |
| Chat tool toolbar | Yes | File · Search · Image · OCR · Browse · Mic · Talk |
| Browse URL dialog | Yes | Portable Chromium from Chat |
| Caps switch descriptions | Yes | Caps ▾ popover |
| Mode help (?) | Yes | Plan vs Action dialog |
| Feature directory | Yes | Help → full inventory → Open page |
| Settings sections | Yes | Appearance · Chat & safety · Image · Providers |
| Test search | Yes | Settings header action |
| Usage on chat status | Yes | Composer status line |
| Home health strip | Yes | API · knowledge · approvals · patches |
| Provider capability matrix | Yes | Settings (honest chat/stream/images/vision) |
| Image model presets + test | Yes | Settings · Test image gen |
| Unverified claim detection | Yes | Chat injects system_note when success claimed without tools |
| Stop kills terminal | Yes | ■ Stop + `kill_active_terminal` |
| Crash-safe session restore | Yes | Prompt if previous unclean exit |
| Self-improve → Patches (default) | Yes | Settings toggle · safer review queue |
| Secret redaction | Yes | Chat/activity exports |
| Work board | Yes | Sidebar **Work** (Todo/Running/Waiting/Done) |
| Composer draft autosave | Yes | Per-chat `draft` field |
| Jump to latest | Yes | ↓ Latest when scrolled up |
| RAG citations | Yes | Knowledge inject + citation index |
| Knowledge health | Yes | `knowledge_health()` stats |
| Trust unit tests | Yes | `tests/test_trust_parsers.py` |
| Compact / comfortable chat density | Yes | Chat **Comfort** chip · Settings → density |
| Mode / Tasks chips + Caps popover | Yes | Chat top bar |
| Collapsible tool traces | Yes | Transcript (▶ Tools · …) |
| Sidebar hubs (collapsible) | Yes | CHAT / WORK / LIBRARY / SYSTEM |
| Approvals badge | Yes | Sidebar count + red hint |
| Slash commands | Yes | `/plan` `/action` `/image` `/search` `/stop` … |
| Command palette | Yes | **Ctrl+K** |
| Composer + menu | Yes | Attach / image / search / OCR |
| Auto IMAGE_GEN fallback | Yes | When model skips or fakes SVG |
| Onboarding wizard | Yes | First run · Home / Settings |
| UI scale | Yes | Settings 0.9–1.25 |
| Chat empty starters | Yes | Empty transcript chips |
| Self-improve with backup | Yes | `BACKUP` / `SELF_IMPROVE` / `ROLLBACK` · `data/backups/self_improve/` |
| Chat timestamps | Yes | Message bubbles |
| Chat rename / pin / branch | Yes | Title · ⋯ · overflow |
| Copy / Edit / Reply / Regen | Yes | Under messages |
| Grok-style chat chrome | Yes | Tabs · Live · ⋯ · message-first |
| Visible Mode / Approvals / Caps bar | Yes | Chat row 2 |
| Plan / Action mode | Yes | Mode segment |
| Company task approval manual\|auto | Yes | Tasks segment · CEO |
| Tool approval toggle | Yes | Chat bar · Approvals · Settings |
| Capability switches | Yes | Terminal · Skills · MCP · Laptop · Workflow · Safety |
| Chat scroll (stick bottom + wheel) | Yes | Transcript |
| Model params / context window | Yes | ⋯ → Params |
| Provider + model search | Yes | Chat row 1 |
| High-contrast chrome themes | Yes | `themes.py` UI palette |
| Portable Chromium browser | Yes | `BROWSER` · `./browsers` · Launch auto-setup |
| Local Knowledge RAG | Yes | Knowledge · hybrid FTS + embeddings |
| Folder auto-watch | Yes | Knowledge |
| Web search | Yes | `WEB_SEARCH` · APIs + free backends · auto page-read (`fetch: N`) |
| Web fetch | Yes | `WEB_FETCH` · HTTP GET/POST any URL / API |
| Deep research | Yes | `DEEP_RESEARCH` · multi-source open + follow links → brief |
| Web crawl | Yes | `WEB_CRAWL` · BFS crawl with depth/page limits |
| Web scrape | Yes | `WEB_SCRAPE` · text / links / tables / CSS |
| Web download | Yes | `WEB_DOWNLOAD` · files → data/browser_downloads |
| Live browser | Yes | Persistent Chromium session: goto/click/fill/text/screenshot/links (headed optional) |
| Clipboard smart attach | Yes | Background watch |
| Continuous voice | Yes | 🎙 · Settings mic mode=toggle · 1.27.84 |
| Mic STT + TTS speak | Yes | 🎤 / 🔊 / Ctrl+M · Settings Voice · 1.27.84 |
| Screen OCR | Yes | OCR · `OCR` blocks |
| Patch review | Yes | Patches page · `PATCH_REVIEW` |
| Scheduled agents | Yes | Schedule page |
| Multi-chat tabs | Yes | Tab bar |
| Stop generation | Yes | ■ Stop |
| Agent activity timeline | Yes | Live → Agents |
| Streaming replies | Yes | Settings |
| Image generation | Yes | `IMAGE_GEN` · Ctrl+G · not SVG fakes |
| Tool budgets | Yes | Usage / budgets |
| Usage meter | Yes | Usage page |
| Multi-theme | Yes | Settings |
| Multi-chat store | Yes | Chats page |
| Memory | Yes | Memory page |
| Projects + outputs | Yes | Projects |
| Company + CEO goals | Yes | Company · CEO |
| Background orchestrator | Yes | Chat stays free |
| Workflow / org tree | Yes | Workflow page · Use workflow |
| Skills catalog + on/off | Yes | Skills manager |
| MCP + marketplace | Yes | MCP · Marketplace |
| Laptop GUI control | Yes | Screenshot · GUI · clipboard · windows |
| Attachments + large-file choice | Yes | Composer 📎 |
| Portable PyInstaller build | Yes | `build_portable.ps1` |
| Launch native ensure | Yes | Launch.bat |

## Self-improve (quick)

See [SELF_IMPROVE.md](SELF_IMPROVE.md) and [TOOLS_PROTOCOL.md](TOOLS_PROTOCOL.md).

## Knowledge (quick)

1. Knowledge → Index file/folder  
2. Ask in Chat (chunks injected)  
3. Or `<<<KNOWLEDGE>>>` blocks  

## Browser (quick)

Run **Launch.bat** (auto-installs Chromium once into `./browsers`).

```
<<<BROWSER>>>
action: screenshot
url: https://example.com
<<<END_BROWSER>>>
```
