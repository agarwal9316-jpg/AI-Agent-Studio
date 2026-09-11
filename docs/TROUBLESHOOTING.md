# Troubleshooting

**App version:** see `app/version.py` · logs under `data/logs/` (1.27.37+).

| Problem | Fix |
|---------|-----|
| **Trackpad scrolling feels jerky / broken** | Fixed in **1.27.37** -- new cross-platform smooth scroller with animated spring physics, momentum/inertia for trackpad flings, high-precision trackpad support (Surface, MacBook, Dell). Uses `apply_smooth_scroll()` with `animate=True, momentum=True`. Hold **Shift** for horizontal scroll on supported areas. |
| **App fails to launch / circular import errors** | Fixed in **1.27.36** -- folder reorganization corrupted 17 __init__.py files with UTF-16 BOM garbage and broke import paths. Run .venv/Scripts/python -m app from project root. If still fails, delete __pycache__ dirs and re-run.
| Launch.bat closes immediately | Path has spaces — use current Launch.bat (calls venv python directly). Open `data\last_launch_error.txt`. |
| **Window flickers then disappears** | Fixed in **1.27.19** — previous anti-flicker used `withdraw`+alpha 0 and never re-showed on some PCs. Update source and use **Launch.bat**. |
| **Blank white screen when switching pages** | Fixed in **1.27.35** — Chat page set content bg to `#f7f7f8`; other pages appeared white. Persistent background frame now stays at bottom. Update to 1.27.35+. |
| **Startup crash: “Too early to use font: no default root window”** | Fixed in **1.27.35** — `AppWindow.__init__` now sets `tkinter._default_root = self` before any CTkFont creation. Update to 1.27.35+. |
| **Crash: “Variable master not specified”** | Fixed in **1.27.35** — all `ctk.StringVar()`, `ctk.BooleanVar()`, etc. calls now include explicit `master=` parameter. Update to 1.27.35+. |
| Module not found | `.\.venv\Scripts\pip install -r requirements.txt` |
| LLM fails | Settings: API key / base URL / model; or use mock runs without a key |
| **Deepseek works in Chat but Org AI fails** | Chat **streams** short answers; Org AI used to ask for **one huge non-stream JSON** (long wait → NVIDIA **504/timeout**). **1.27.22+** Org AI uses **streaming like Chat**. Prefer smaller seats; `meta/llama-3.1-8b-instruct` still safest. |
| **Org ✨ AI create timed out / stuck 2+ min** | Check **`data/logs/org_ai.log`**. On NVIDIA: deepseek non-stream often **504**; mistral-large may **404**. Use **`meta/llama-3.1-8b-instruct`** + Save LLM settings. **1.27.21+** fallbacks. |
| **Org ✨ AI create timed out** | Prefer small/medium seats; open **`data/logs/org_ai.log`**. Keep dialog open. |
| Org workers missing system prompt | Open Selection details — prompts shown/editable · re-run AI create on 1.27.18+ (forces fill) · ⚙ Full configure |
| HTTP 400 “System message must be at the beginning” | Fixed in **1.12.1** — restart app; was extra `system` msg from context trim |
| Model list empty | ↻ models · check provider key · OpenRouter vs OpenAI base URL |
| Image gen fails / model writes SVG | Action mode · real `IMAGE_GEN` · image-capable model (e.g. OpenAI `dall-e-3`) · see FEATURES / TOOLS_PROTOCOL |
| Top bar unreadable | Use Readable Dark/Light · v1.7.7+ chrome styles · restart after update |
| Browser tool missing Chromium | Run Launch.bat once to install into `./browsers` |
| Tools not running | Switch Mode to **action** (not plan) |
| Tools waiting forever | Check **Approvals** · Tool approval toggle · approve pending |
| Company tasks stuck | CEO Approvals · or set Tasks to **auto** · **v1.10.1+** orphaned `running` tasks auto-fail on restart |
| Work badge shows “N run” forever | Previous session died mid-task — restart app (auto-recover) or open Work and cancel/fail tasks |
| Says “No API key” but Providers has a key | **v1.10.1+** fixed — status uses provider **or** Settings key; switch active provider/key in Settings |
| Search only returns Wikipedia | **v1.13+** parallel engines + Chromium Bing fallback. Still best with free **Tavily** key in Settings → Web search. Prefer specific queries (product + year). |
| Want ChatGPT-like web research | Settings → Web search → Engine **Tavily** + API key · enable **Auto-open top pages** · Action mode · ask model to search |
| Need full site interaction | Settings → Browser headed ON for CAPTCHA/login · Persistent profile ON · Action mode · model uses `<<<BROWSER>>>` click/fill |
| Model says “no internet” | False — use Action mode + Caps tools on; tools: WEB_SEARCH, WEB_FETCH, BROWSER, TERMINAL |
| “Media link could not be downloaded” | Site blocks hotlinking / needs login / not a direct image file. Open link below · prefer direct `.jpg`/`.png` · or BROWSER screenshot |
| Self-improve does nothing | Need `path: app/...` and body after `---` · invalid blocks now show a help note in chat |
| Self-improve rolled back | Syntax error in patch — see tool message · fix and retry |
| TclError / activity panel after close | Fixed in **1.10.1** (activity listener guards destroyed widgets) |
| Portable missing | Run `build_portable.ps1` first |
| Reset everything | Close app · delete `data\` (optional: `browsers\`) |

### Historical: Launch.bat path crash

Folder path contains spaces (`AI Working`). Old `powershell -File` split the path. Current launcher avoids that.
