# Research: Optional Grok CLI session reuse (#20)

**Date:** 2026-09-11  
**App head at research:** 1.27.84  
**Decision:** **SKIP — do not implement**  
**Deliverable version:** 1.27.85 (docs + PENDING status only; no session/cookie code)

---

## 1. What “Grok CLI” means in this codebase

| Sense | In AI Agent Studio today |
|-------|--------------------------|
| **Official Grok Build CLI** (`grok` from [x.ai/cli](https://x.ai/cli) / [docs.x.ai/build](https://docs.x.ai/build/overview)) | **Not embedded.** Studio is a separate desktop GUI with its own OpenAI-compatible LLM client. |
| **“Grok-style” harness** | Present: `app/services/agent_harness/*`, skills/rules/hooks discovery under `~/.grok/`, capability manual contrasting Grok Build host vs Studio (`capability_manual.grok_parity_matrix`). |
| **Direct xAI API path (#1)** | **Done.** Provider `xai` → `https://api.x.ai/v1`; `activate_grok_as_agent(prefer="xai")`; keys from `console.x.ai` / `XAI_API_KEY`. Explicit UX copy: *“desktop, no CLI”* and *“a grok.com website login is NOT the same as an API key.”* |
| **Browser / cookie “session”** | Studio’s browser tool keeps its **own** Chromium profile cookies for general web automation — unrelated to xAI auth. |

Codebase search (`grok cli`, `xai cli`, `console.x.ai`, `auth.json`, session reuse) finds **no** existing or stubbed path that reuses a Grok CLI login or console.x.ai cookies for Studio chat. Mentions of `~/.grok` are limited to **skills, rules, hooks, MCP config** — not credentials.

---

## 2. Official xAI CLI / session mechanisms (external)

As of 2026-09 (docs.x.ai / Grok Build):

1. **Auth for the official CLI**
   - `grok login` (browser OAuth at auth.x.ai) or `grok login --device-auth`
   - Credentials cached in `~/.grok/auth.json` (CLI-owned; auto-refresh)
   - **Automation / third-party agents:** documented path is **`XAI_API_KEY`** against **`https://api.x.ai/v1`**
2. **Conversation session reuse (within the CLI)**
   - Local session transcripts; flags `--resume` / `-r`, `--continue` / `-c`, `grok sessions …`
   - This is **CLI conversation continuity**, not an API for other apps to borrow login state.
3. **IDE / host integration**
   - Documented embedding path is **ACP** (`grok agent stdio`) — credentials stay with the CLI process.
4. **Power-user curl note (CLI chat proxy)**
   - Internal/dev docs show calling `cli-chat-proxy.grok.com` with a token from `auth.json` plus headers such as `X-XAI-Token-Auth: xai-grok-cli`.
   - That documents how the **official CLI** talks to its proxy; it is **not** a supported product API for third-party desktop apps to impersonate the CLI.

There is **no** official “export session cookie / reuse console.x.ai browser session in your app” product.

---

## 3. Product / ToS / AUP risk

| Approach | Allowed for Studio? | Why |
|----------|---------------------|-----|
| **API key** from console.x.ai → `api.x.ai` | **Yes (official)** | Already shipped as #1; matches Enterprise/API terms and docs. |
| **Scrape console.x.ai / grok.com** or reuse **browser cookies** without a key | **No** | SpaceXAI Acceptable Use Policy (effective 2026-08-14) prohibits scraping/harvesting and *“Accessing the Services through unauthorized automated or non-human means, whether through a bot, script, or otherwise”*; also forbids bypassing protective measures / rate limits. |
| **Read `~/.grok/auth.json` and call CLI proxy as if Studio were Grok CLI** | **Not clearly allowed** | Undocumented for third-party products; presents Studio as the CLI (`X-XAI-Token-Auth: xai-grok-cli`); fragile (short-lived tokens, refresh owned by CLI); blurs subscription vs API billing. Gray-area tools exist in the wild; that does **not** make it a clear product/legal green light. |
| **Shell out to `grok -p` / ACP** | **Possible product idea, out of scope for #20** | Would use the official binary with *its* auth — not “session hijack.” Different feature (embed Grok Build), heavy dependency, duplicates Studio’s own harness. Not what PENDING #20 framed as research-first legal gate. |

**Honest conclusion:** Cookie/console session reuse and silent `auth.json` hijack are **disallowed or unclear**. Prefer the existing API-key path.

---

## 4. Decision

**Mark PENDING #20 as `skipped`.**

- Do **not** implement cookie scraping, console.x.ai automation, or reading/replaying `~/.grok/auth.json` / CLI proxy tokens inside Studio.
- Keep directing users to **Home → Use Grok** / Settings → xAI Grok with a **console.x.ai API key** (and optional `XAI_API_KEY` env).
- Optional future (separate task, only if product wants it): document ACP / “install Grok Build CLI alongside Studio” as an **external** workflow — still without credential theft.

---

## 5. Sources consulted

- In-repo: `app/core/services/llm/providers.py` (`activate_grok_as_agent`), `docs/PENDING_TASKS.md` #1/#20, agent harness `~/.grok` discovery, `capability_manual.py`
- [docs.x.ai/build/overview](https://docs.x.ai/build/overview) — install, `XAI_API_KEY`, API examples
- [docs.x.ai/build/cli/reference](https://docs.x.ai/build/cli/reference) — `grok login` / `--resume` / sessions
- [x.ai/legal/acceptable-use-policy](https://x.ai/legal/acceptable-use-policy) — scraping / unauthorized automated access
- Grok Build auth / headless user-guide material (auth.json for CLI; API key for automation)

---

## 6. What shipped for this task

- This research document
- `docs/PENDING_TASKS.md` status → **skipped** + short rationale
- `docs/CHANGELOG.md` + patch bump **1.27.85** (docs deliverable only)
- No runtime auth changes
