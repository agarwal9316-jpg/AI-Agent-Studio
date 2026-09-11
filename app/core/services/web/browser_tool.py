"""
Full internet browser for the agent — persistent Chromium session.

Unlike one-shot page opens, this keeps a live browser (Playwright) so the model can:
  goto → click → type → scroll → screenshot → text  (multi-step, like a human)

Portable Chromium: <app_root>/browsers via PLAYWRIGHT_BROWSERS_PATH.
Optional headed mode + persistent profile under data/browser_profile.

Anti-bot / captcha strategy (1.27.4+):
  1. Prefer modern headless (Chrome --headless=new) with stealth init scripts
  2. Detect captcha / challenge / anti-bot pages after navigation
  3. Auto-fallback to headed (visible) browser with the same profile cookies
  4. wait_for_captcha: pause until user solves challenge or timeout
"""

from __future__ import annotations

import os
import re
import shutil
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable

from app.paths import app_root, data_dir

BROWSER_RE = re.compile(
    r"<<<BROWSER>>>\s*(.*?)\s*<<<END_BROWSER>>>",
    re.DOTALL | re.IGNORECASE,
)

# Session lock — Playwright sync API is not free-threaded
_session_lock = threading.RLock()
_session: dict[str, Any] | None = None

# Last challenge detection (for UI / callers)
_last_challenge: dict[str, Any] = {}

# Stealth init script applied to every new page/context
_STEALTH_JS = r"""
(() => {
  try {
    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
  } catch (e) {}
  try {
    // Fake chrome runtime
    window.chrome = window.chrome || { runtime: {} };
  } catch (e) {}
  try {
    const originalQuery = window.navigator.permissions && window.navigator.permissions.query;
    if (originalQuery) {
      window.navigator.permissions.query = (parameters) => (
        parameters && parameters.name === 'notifications'
          ? Promise.resolve({ state: Notification.permission })
          : originalQuery(parameters)
      );
    }
  } catch (e) {}
  try {
    Object.defineProperty(navigator, 'plugins', {
      get: () => [1, 2, 3, 4, 5],
    });
  } catch (e) {}
  try {
    Object.defineProperty(navigator, 'languages', {
      get: () => ['en-US', 'en'],
    });
  } catch (e) {}
  try {
    // WebGL vendor unmask sometimes used for bot checks
    const getParameter = WebGLRenderingContext.prototype.getParameter;
    WebGLRenderingContext.prototype.getParameter = function(parameter) {
      if (parameter === 37445) return 'Intel Inc.';
      if (parameter === 37446) return 'Intel Iris OpenGL Engine';
      return getParameter.call(this, parameter);
    };
  } catch (e) {}
})();
"""

# Text/url patterns that indicate captcha or bot wall
_CHALLENGE_PATTERNS = (
    r"captcha",
    r"recaptcha",
    r"hcaptcha",
    r"cf-turnstile",
    r"cloudflare",
    r"attention required",
    r"just a moment",
    r"checking your browser",
    r"verify you are human",
    r"are you a robot",
    r"anti-bot",
    r"verification failed",
    r"verification in progress",
    r"access denied",
    r"unusual traffic",
    r"please complete the security check",
    r"enable javascript and cookies",
    r"ray id",
    r"challenge-platform",
    r"vpn may cause",
    r"bot detection",
)


def browsers_dir() -> Path:
    d = app_root() / "browsers"
    d.mkdir(parents=True, exist_ok=True)
    return d


def browser_profile_dir() -> Path:
    d = data_dir() / "browser_profile"
    d.mkdir(parents=True, exist_ok=True)
    return d


def browser_downloads_dir() -> Path:
    d = data_dir() / "browser_downloads"
    d.mkdir(parents=True, exist_ok=True)
    return d


def ensure_playwright_env() -> Path:
    path = browsers_dir()
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(path.resolve())
    return path


def browser_shots_dir() -> Path:
    d = data_dir() / "browser_shots"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _cfg() -> dict[str, Any]:
    try:
        from app.core.services.data.storage import load_config

        return load_config()
    except Exception:  # noqa: BLE001
        return {}


def tool_instructions() -> str:
    cfg = _cfg()
    headed = bool(cfg.get("browser_headed", False))
    mode = "HEADED (visible window)" if headed else "headless → auto headed on block"
    return f"""
## Full browser — live Chromium session ({mode})

You have a **persistent browser on this PC** (not a fake). Use it for any website
the way a human would: open URL → read → click → type → screenshot.

**Anti-bot:** headless first; if captcha/anti-bot is detected, the session
auto-switches to a **headed** (visible) browser with the same profile. For
user captchas use action: wait_for_captcha (user solves in the window).

### Open / read
<<<BROWSER>>>
action: goto
url: https://example.com
auto_headed: true
<<<END_BROWSER>>>

# For JavaScript-heavy sites (SPAs, React, Vue, AI generators, etc.) use
# wait_until: networkidle  — waits for all network requests to finish:
<<<BROWSER>>>
action: goto
url: https://example.com
wait_until: networkidle
wait_ms: 3000
<<<END_BROWSER>>>

<<<BROWSER>>>
action: detect_challenge
<<<END_BROWSER>>>

<<<BROWSER>>>
action: wait_for_captcha
timeout: 180000
<<<END_BROWSER>>>

<<<BROWSER>>>
action: switch_headed
<<<END_BROWSER>>>

<<<BROWSER>>>
action: text
selector: body
<<<END_BROWSER>>>

<<<BROWSER>>>
action: screenshot
full_page: true
<<<END_BROWSER>>>

### Interact (multi-step — session is kept open between blocks)
<<<BROWSER>>>
action: click
selector: a.login
<<<END_BROWSER>>>

<<<BROWSER>>>
action: fill
selector: input[name=q]
value: python news
<<<END_BROWSER>>>

<<<BROWSER>>>
action: press
key: Enter
<<<END_BROWSER>>>

<<<BROWSER>>>
action: scroll
dy: 800
<<<END_BROWSER>>>

<<<BROWSER>>>
action: wait
wait_ms: 2000
<<<END_BROWSER>>>

<<<BROWSER>>>
action: links
<<<END_BROWSER>>>

<<<BROWSER>>>
action: evaluate
script: document.title
<<<END_BROWSER>>>

<<<BROWSER>>>
action: download
url: https://example.com/file.pdf
<<<END_BROWSER>>>

<<<BROWSER>>>
action: reload
<<<END_BROWSER>>>

### Session control
<<<BROWSER>>>
action: status
<<<END_BROWSER>>>

<<<BROWSER>>>
action: close
<<<END_BROWSER>>>

**Actions:** goto | reload | text | html | screenshot | pdf | click | fill | type | press |
save_image | screenshot_element | frames | evaluate |

### iframe / frame targeting (JS generators like Perchance)
<<<BROWSER>>>
action: fill
selector: #input
value: a red fox in snow
<<<END_BROWSER>>>

<<<BROWSER>>>
action: click
selector: button:has-text("generate")
<<<END_BROWSER>>>

# After generate, capture image (path is shown in chat):
<<<BROWSER>>>
action: save_image
frame: outputIframeEl
selector: img
<<<END_BROWSER>>>

<<<BROWSER>>>
action: screenshot
full_page: false
<<<END_BROWSER>>>

**Actions (extended):** goto | reload | text | html | screenshot | pdf | click | fill | type | press |
save_image | screenshot_element | frames |
scroll | wait | links | evaluate | download | content | status | close

**wait_until values:** domcontentloaded (default, fast) | load | networkidle (best for JS-heavy / SPA sites)

**Rules for full internet use:**
1. Prefer WEB_SEARCH first to find URLs, then BROWSER to open and interact.
2. Or WEB_FETCH for simple GET of APIs / static pages (no JS).
3. Keep the session open across tool rounds — do not close until done.
4. **For JS-heavy sites** (AI generators, React apps, SPAs): always use
   `wait_until: networkidle` on `goto`, then add a `wait` of 2000-5000 ms
   before reading text or taking a screenshot — the page renders after load.
5. Terminal curl is also available when Terminal is on (Action mode).
6. If a CAPTCHA appears (screenshot), tell the user to complete it in headed mode
   (Settings → Browser headed ON) or provide another approach.
7. If `status` reports `"session": "stale"` do a `close` then a fresh `goto`.

Profile dir persists cookies under data/browser_profile when enabled.
""".strip()


def extract_browser_blocks(text: str) -> list[dict[str, str]]:
    keys = (
        "action",
        "url",
        "selector",
        "full_page",
        "wait_ms",
        "wait_until",
        "value",
        "text",
        "key",
        "script",
        "dx",
        "dy",
        "n",
        "timeout",
        "headed",
        "new_tab",
        "frame",
        "iframe",
        "auto_headed",
        "wait_captcha",
    )
    out = []
    for m in BROWSER_RE.finditer(text or ""):
        body = (m.group(1) or "").strip()
        meta: dict[str, str] = {
            "action": "goto",
            "url": "",
            "selector": "body",
            "full_page": "false",
            "wait_ms": "1500",
            "wait_until": "",  # empty = default (domcontentloaded)
            "value": "",
            "text": "",
            "key": "",
            "script": "",
            "dx": "0",
            "dy": "600",
            "n": "30",
            "timeout": "60000",
            "headed": "",
            "new_tab": "false",
            "frame": "",
            "iframe": "",
            "auto_headed": "true",
            "wait_captcha": "false",
        }
        for line in body.splitlines():
            if ":" not in line:
                continue
            k, v = line.split(":", 1)
            k, v = k.strip().lower(), v.strip()
            if k in keys:
                meta[k] = v
            elif k in ("content", "input"):
                meta["value"] = v
        # multi-line script after script:
        if "script:" in body.lower() and not meta.get("script"):
            parts = re.split(r"(?im)^script:\s*", body, maxsplit=1)
            if len(parts) == 2:
                meta["script"] = parts[1].strip()
        if not meta.get("url") and body and body.startswith("http"):
            meta["url"] = body.splitlines()[0].strip()
        # value can also be whole remaining for fill
        if meta.get("action") in ("fill", "type") and not meta.get("value") and meta.get("text"):
            meta["value"] = meta["text"]
        if meta.get("url") or meta.get("action"):
            out.append(meta)
    return out


def find_local_chromium_exe() -> Path | None:
    """Locate portable chrome.exe / chrome under app browsers/ (any build number)."""
    root = browsers_dir()
    # Prefer full chrome over headless_shell for better site compatibility
    candidates: list[Path] = []
    for p in root.rglob("chrome.exe"):
        if p.is_file() and "headless_shell" not in str(p).lower():
            candidates.append(p)
    for p in root.rglob("chrome.exe"):
        if p.is_file() and p not in candidates:
            candidates.append(p)
    for p in root.rglob("chrome"):
        if p.is_file() and os.access(p, os.X_OK) and "headless" not in p.name.lower():
            candidates.append(p)
    # Prefer higher version folder names (chromium-1228 > chromium-1223)
    def _score(path: Path) -> tuple[int, int, str]:
        s = str(path)
        import re as _re

        m = _re.search(r"chromium(?:_headless_shell)?-(\d+)", s, _re.I)
        ver = int(m.group(1)) if m else 0
        full = 1 if "headless_shell" not in s.lower() else 0
        return (full, ver, s)

    if not candidates:
        return None
    candidates.sort(key=_score, reverse=True)
    return candidates[0]


def _chromium_installed() -> bool:
    if find_local_chromium_exe() is not None:
        return True
    # Also accept Playwright default cache if present
    try:
        ensure_playwright_env()
        from playwright.sync_api import sync_playwright  # type: ignore

        pw = sync_playwright().start()
        try:
            exe = Path(pw.chromium.executable_path or "")
            return exe.is_file()
        finally:
            pw.stop()
    except Exception:  # noqa: BLE001
        return False


def install_chromium() -> dict[str, Any]:
    ensure_playwright_env()
    try:
        import subprocess
        import sys

        cmd = [sys.executable, "-m", "playwright", "install", "chromium"]
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600,
            env={**os.environ, "PLAYWRIGHT_BROWSERS_PATH": str(browsers_dir().resolve())},
        )
        ok = proc.returncode == 0 and _chromium_installed()
        return {
            "ok": ok,
            "returncode": proc.returncode,
            "stdout": (proc.stdout or "")[-2000:],
            "stderr": (proc.stderr or "")[-2000:],
            "browsers_path": str(browsers_dir().resolve()),
            "chromium_found": _chromium_installed(),
        }
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e), "browsers_path": str(browsers_dir())}


def _bool(v: Any, default: bool = False) -> bool:
    if v is None or v == "":
        return default
    return str(v).strip().lower() in ("1", "true", "yes", "on")


def _close_session_unlocked() -> None:
    global _session
    if not _session:
        return
    try:
        ctx = _session.get("context")
        if ctx:
            ctx.close()
    except Exception:  # noqa: BLE001
        pass
    try:
        browser = _session.get("browser")
        if browser:
            browser.close()
    except Exception:  # noqa: BLE001
        pass
    try:
        pw = _session.get("playwright")
        if pw:
            pw.stop()
    except Exception:  # noqa: BLE001
        pass
    _session = None


def close_browser_session() -> dict[str, Any]:
    with _session_lock:
        _close_session_unlocked()
    return {"ok": True, "action": "close", "session": "closed"}


def _is_page_alive(page: Any) -> bool:
    """Lightweight liveness check — returns False if the page/context is closed or crashed."""
    try:
        _ = page.url  # raises if context is closed
        page.evaluate("1")  # raises if renderer process is dead
        return True
    except Exception:  # noqa: BLE001
        return False


def _clear_profile_lock() -> None:
    """Remove Chromium's SingletonLock and CrashpadMetrics files that block reuse after a crash."""
    profile = browser_profile_dir()
    for lockfile in ("SingletonLock", "SingletonCookie", "SingletonSocket"):
        lf = profile / lockfile
        try:
            if lf.exists():
                lf.unlink(missing_ok=True)
        except Exception:  # noqa: BLE001
            pass
    # Also clear Crashpad metadata that can prevent relaunch
    crashpad = profile / "Crashpad" / "metadata"
    try:
        if crashpad.exists():
            crashpad.unlink(missing_ok=True)
    except Exception:  # noqa: BLE001
        pass


def _chrome_user_agent() -> str:
    """Prefer a modern Chrome UA (helps with anti-bot fingerprint)."""
    return (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    )


def _launch_args(*, headed: bool) -> list[str]:
    args = [
        "--disable-blink-features=AutomationControlled",
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-infobars",
        "--disable-background-timer-throttling",
        "--disable-backgrounding-occluded-windows",
        "--disable-renderer-backgrounding",
        "--disable-features=IsolateOrigins,site-per-process",
        "--lang=en-US",
        # WebGL (AI generators / canvas sites)
        "--use-gl=angle",
        "--use-angle=swiftshader",
        "--enable-webgl",
        "--ignore-gpu-blocklist",
        "--enable-webgl2-compute-context",
    ]
    if not headed:
        # Chrome's modern headless (closer to real Chrome than old headless)
        args.append("--headless=new")
        args.append("--window-size=1365,900")
    else:
        # Headed: slightly off-primary so it feels "background" but user can solve captcha
        args.append("--window-position=80,60")
        args.append("--window-size=1280,900")
        # Do not steal focus aggressively if OS allows
        args.append("--disable-background-mode")
    return args


def _apply_stealth(context: Any, page: Any) -> None:
    try:
        context.add_init_script(_STEALTH_JS)
    except Exception:  # noqa: BLE001
        pass
    try:
        page.add_init_script(_STEALTH_JS)
    except Exception:  # noqa: BLE001
        pass
    try:
        # Extra headers
        context.set_extra_http_headers(
            {
                "Accept-Language": "en-US,en;q=0.9",
                "Upgrade-Insecure-Requests": "1",
            }
        )
    except Exception:  # noqa: BLE001
        pass


def detect_page_challenge(page: Any = None) -> dict[str, Any]:
    """
    Detect captcha / Cloudflare / anti-bot challenge on the current page (+ frames).
    Returns {blocked, kind, evidence, url, title}.
    """
    global _last_challenge
    if page is None and _session:
        page = _session.get("page")
    if page is None:
        return {"blocked": False, "kind": "", "evidence": [], "url": "", "title": ""}

    evidence: list[str] = []
    kind = ""
    try:
        url = page.url or ""
        title = page.title() or ""
    except Exception:  # noqa: BLE001
        url, title = "", ""

    blobs: list[str] = [url, title]
    try:
        body = page.inner_text("body", timeout=4000) or ""
        blobs.append(body[:12000])
    except Exception:  # noqa: BLE001
        pass
    try:
        html = page.content() or ""
        blobs.append(html[:20000])
    except Exception:  # noqa: BLE001
        pass
    # Nested frames (Perchance anti-bot lives here)
    try:
        for fr in page.frames:
            try:
                t = fr.inner_text("body", timeout=1500) or ""
                if t.strip():
                    blobs.append(t[:4000])
            except Exception:  # noqa: BLE001
                pass
            try:
                fu = fr.url or ""
                if fu:
                    blobs.append(fu)
            except Exception:  # noqa: BLE001
                pass
    except Exception:  # noqa: BLE001
        pass

    text = "\n".join(blobs).lower()
    for pat in _CHALLENGE_PATTERNS:
        if re.search(pat, text, re.I):
            evidence.append(pat)
            if not kind:
                if "captcha" in pat or "recaptcha" in pat or "hcaptcha" in pat or "turnstile" in pat:
                    kind = "captcha"
                elif "cloudflare" in pat or "just a moment" in pat or "ray id" in pat:
                    kind = "cloudflare"
                elif "anti-bot" in pat or "verification" in pat or "vpn" in pat:
                    kind = "anti_bot"
                else:
                    kind = "challenge"

    # DOM markers
    try:
        markers = page.evaluate(
            """() => {
              const sels = [
                'iframe[src*="recaptcha"]', 'iframe[src*="hcaptcha"]',
                'iframe[src*="turnstile"]', '.g-recaptcha', '#cf-challenge-stage',
                '[data-sitekey]', 'iframe[src*="challenge"]'
              ];
              const hit = [];
              for (const s of sels) {
                if (document.querySelector(s)) hit.push(s);
              }
              return hit;
            }"""
        )
        if markers:
            evidence.extend([f"dom:{m}" for m in markers])
            if not kind:
                kind = "captcha"
    except Exception:  # noqa: BLE001
        pass

    blocked = bool(evidence)
    out = {
        "blocked": blocked,
        "kind": kind if blocked else "",
        "evidence": evidence[:12],
        "url": url,
        "title": title,
        "headed": bool(_session and _session.get("headed")),
    }
    _last_challenge = out
    return out


def last_challenge() -> dict[str, Any]:
    return dict(_last_challenge or {})


def _ensure_session(headed: bool | None = None) -> dict[str, Any]:
    """Start or reuse Playwright browser + page, with health checks + stealth."""
    global _session
    cfg = _cfg()
    want_headed = bool(cfg.get("browser_headed", False)) if headed is None else bool(headed)
    persistent = bool(cfg.get("browser_persistent", True))

    if _session and _session.get("page"):
        # Recreate if headed mode changed
        if _session.get("headed") != want_headed:
            _close_session_unlocked()
        else:
            if not _is_page_alive(_session["page"]):
                _close_session_unlocked()
            else:
                return _session

    ensure_playwright_env()
    from playwright.sync_api import sync_playwright  # type: ignore

    launch_args = _launch_args(headed=want_headed)
    viewport = {"width": 1365, "height": 900}
    user_agent = _chrome_user_agent()

    local_exe = find_local_chromium_exe()
    exe_kwargs: dict[str, Any] = {}
    if local_exe is not None and local_exe.is_file():
        exe_kwargs["executable_path"] = str(local_exe.resolve())

    last_err: Exception | None = None
    for attempt in range(3):
        try:
            pw = sync_playwright().start()
            use_exe = dict(exe_kwargs) if attempt < 2 and exe_kwargs else {}
            if attempt >= 1:
                _clear_profile_lock()
            common_ctx = {
                "viewport": viewport,
                "user_agent": user_agent,
                "accept_downloads": True,
                "locale": "en-US",
                "timezone_id": "America/New_York",
                "color_scheme": "light",
                "device_scale_factor": 1,
                "has_touch": False,
                "is_mobile": False,
                "java_script_enabled": True,
            }
            if persistent:
                context = pw.chromium.launch_persistent_context(
                    user_data_dir=str(browser_profile_dir().resolve()),
                    headless=not want_headed,
                    args=launch_args,
                    ignore_default_args=["--enable-automation"],
                    **common_ctx,
                    **use_exe,
                )
                browser = None
                page = context.pages[0] if context.pages else context.new_page()
            else:
                browser = pw.chromium.launch(
                    headless=not want_headed,
                    args=launch_args,
                    ignore_default_args=["--enable-automation"],
                    **use_exe,
                )
                context = browser.new_context(**common_ctx)
                page = context.new_page()
            _apply_stealth(context, page)
            last_err = None
            break
        except Exception as launch_err:  # noqa: BLE001
            last_err = launch_err
            try:
                pw.stop()
            except Exception:  # noqa: BLE001
                pass
            _clear_profile_lock()
            continue
    if last_err is not None:
        raise RuntimeError(
            f"Browser failed to start after retries. "
            f"local_exe={local_exe} error={last_err}"
        ) from last_err

    _session = {
        "playwright": pw,
        "browser": browser,
        "context": context,
        "page": page,
        "headed": want_headed,
        "persistent": persistent,
        "fallback_from_headless": False,
        "stealth": True,
        "chrome_mode": "headed" if want_headed else "headless=new",
    }
    return _session


def switch_to_headed(
    *,
    reason: str = "",
    reload_url: str = "",
) -> dict[str, Any]:
    """
    Close headless session and reopen headed with the same persistent profile
    (cookies/storage retained). Used when captcha/anti-bot blocks headless.
    """
    with _session_lock:
        url = reload_url
        if not url and _session and _session.get("page"):
            try:
                url = _session["page"].url or ""
            except Exception:  # noqa: BLE001
                url = ""
        _close_session_unlocked()
        sess = _ensure_session(headed=True)
        sess["fallback_from_headless"] = True
        sess["fallback_reason"] = reason or "blocked_in_headless"
        page = sess["page"]
        if url and str(url).startswith("http"):
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(1500)
            except Exception as e:  # noqa: BLE001
                return {
                    "ok": False,
                    "action": "switch_headed",
                    "error": str(e),
                    "headed": True,
                    "reason": reason,
                    **_page_meta(page),
                }
        challenge = detect_page_challenge(page)
        return {
            "ok": True,
            "action": "switch_headed",
            "headed": True,
            "reason": reason,
            "reloaded": bool(url),
            "challenge": challenge,
            "message": (
                "Switched to visible browser. If a captcha is shown, complete it "
                "in the Chrome window, then continue."
            ),
            **_page_meta(page),
        }


def wait_for_captcha_clear(
    *,
    timeout_ms: int = 180_000,
    poll_ms: int = 2000,
    on_progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """
    Ensure headed mode, then poll until challenge is gone or timeout.
    User solves captcha in the visible window.
    """
    def prog(msg: str) -> None:
        if on_progress:
            try:
                on_progress(msg)
            except Exception:  # noqa: BLE001
                pass

    with _session_lock:
        if not _session or not _session.get("headed"):
            switch_to_headed(reason="wait_for_captcha")
        page = _session["page"] if _session else None
        if not page:
            return {"ok": False, "error": "No browser session", "action": "wait_for_captcha"}

        deadline = time.time() + max(10, timeout_ms / 1000.0)
        prog("Waiting for captcha / challenge to clear — complete it in the browser window…")
        last = detect_page_challenge(page)
        while time.time() < deadline:
            last = detect_page_challenge(page)
            if not last.get("blocked"):
                prog("Challenge cleared")
                return {
                    "ok": True,
                    "action": "wait_for_captcha",
                    "cleared": True,
                    "challenge": last,
                    **_page_meta(page),
                }
            prog(f"Still blocked ({last.get('kind') or 'challenge'})…")
            try:
                page.wait_for_timeout(max(500, poll_ms))
            except Exception:  # noqa: BLE001
                time.sleep(poll_ms / 1000.0)
        return {
            "ok": False,
            "action": "wait_for_captcha",
            "cleared": False,
            "error": "Timeout waiting for captcha / challenge to clear",
            "challenge": last,
            **_page_meta(page),
        }


def ensure_browser(
    *,
    headed: bool | None = None,
    prefer_headless: bool = True,
) -> dict[str, Any]:
    """
    Public helper: open session.
    prefer_headless=True starts headless unless config/browser_headed or headed=True.
    """
    cfg = _cfg()
    if headed is None:
        if cfg.get("browser_headed"):
            headed = True
        elif prefer_headless:
            headed = False
        else:
            headed = bool(cfg.get("browser_headed", False))
    with _session_lock:
        return _ensure_session(headed=headed)


def _page_meta(page: Any) -> dict[str, Any]:
    try:
        return {"url": page.url, "title": page.title()}
    except Exception:  # noqa: BLE001
        return {"url": "", "title": ""}


def _resolve_wait_until(val: str) -> str:
    """Normalise wait_until values the model might write."""
    val = (val or "").strip().lower().replace("-", "").replace("_", "")
    if val in ("networkidle", "idle", "network"):
        return "networkidle"
    if val in ("load", "loaded"):
        return "load"
    return "domcontentloaded"  # safe default


def _resolve_target(page: Any, cmd: dict[str, Any]):
    """
    Resolve interaction target: main page or a frame.

    frame: optional URL substring, name, or CSS selector for iframe element
           e.g. frame: outputIframeEl  OR  frame: perchance.org
    """
    frame_key = (cmd.get("frame") or cmd.get("iframe") or "").strip()
    if not frame_key:
        return page
    # By iframe element selector (id or css)
    try:
        if frame_key.startswith("#") or frame_key.startswith(".") or " " in frame_key:
            handle = page.query_selector(f"iframe{frame_key}" if frame_key.startswith("#") else frame_key)
            if handle is None and frame_key.startswith("#"):
                handle = page.query_selector(f"iframe{frame_key}")
            if handle is None:
                handle = page.query_selector(frame_key if frame_key.startswith("iframe") else f"iframe{frame_key}")
            if handle is not None:
                fr = handle.content_frame()
                if fr:
                    return fr
        # id without #
        handle = page.query_selector(f"iframe#{frame_key}") or page.query_selector(f"#{frame_key}")
        if handle is not None:
            fr = handle.content_frame()
            if fr:
                return fr
    except Exception:  # noqa: BLE001
        pass
    # Match by URL / name
    try:
        for fr in page.frames:
            name = (fr.name or "")
            url = fr.url or ""
            if frame_key == name or frame_key in url or frame_key in name:
                return fr
    except Exception:  # noqa: BLE001
        pass
    return page


def _run_session_action(cmd: dict[str, Any]) -> dict[str, Any]:  # noqa: C901
    action = (cmd.get("action") or "goto").lower().strip()
    if action == "close":
        return close_browser_session()

    headed_override = None
    if cmd.get("headed") not in (None, ""):
        headed_override = _bool(cmd.get("headed"))

    with _session_lock:
        try:
            sess = _ensure_session(headed=headed_override)
        except Exception as e:  # noqa: BLE001
            # try install once
            if not _chromium_installed():
                inst = install_chromium()
                if not inst.get("ok"):
                    return {"ok": False, "error": f"Chromium missing: {e}; install={inst}"}
                try:
                    sess = _ensure_session(headed=headed_override)
                except Exception as e2:  # noqa: BLE001
                    return {"ok": False, "error": str(e2)}
            else:
                return {"ok": False, "error": f"Browser session failed: {e}"}

        page = sess["page"]

        # ── BUG FIX 3: re-validate the page is alive even after _ensure_session ──
        # _ensure_session may have returned a cached session whose page died between calls.
        if not _is_page_alive(page):
            _close_session_unlocked()
            try:
                sess = _ensure_session(headed=headed_override)
                page = sess["page"]
            except Exception as e3:  # noqa: BLE001
                return {"ok": False, "error": f"Could not recover browser session: {e3}"}

        wait_ms = int(cmd.get("wait_ms") or 1500)
        timeout = int(cmd.get("timeout") or 60000)
        selector = (cmd.get("selector") or "body").strip() or "body"
        full_page = _bool(cmd.get("full_page"))
        url = (cmd.get("url") or "").strip()
        # ── BUG FIX 4: honour the wait_until parameter ──
        wait_until = _resolve_wait_until(cmd.get("wait_until") or "")
        target = _resolve_target(page, cmd)

        try:
            if action == "status":
                meta = _page_meta(page)
                alive = _is_page_alive(page)
                ch = detect_page_challenge(page)
                return {
                    "ok": True,
                    "action": "status",
                    "session": "open" if alive else "stale",
                    "alive": alive,
                    "headed": sess.get("headed"),
                    "persistent": sess.get("persistent"),
                    "chrome_mode": sess.get("chrome_mode"),
                    "stealth": sess.get("stealth"),
                    "fallback_from_headless": sess.get("fallback_from_headless"),
                    "challenge": ch,
                    **meta,
                }

            if action in ("detect_challenge", "detect_captcha", "check_block"):
                ch = detect_page_challenge(page)
                return {
                    "ok": True,
                    "action": "detect_challenge",
                    "blocked": ch.get("blocked"),
                    "kind": ch.get("kind"),
                    "evidence": ch.get("evidence"),
                    "challenge": ch,
                    "headed": sess.get("headed"),
                    **_page_meta(page),
                }

            if action == "reload":
                page.reload(wait_until=wait_until, timeout=timeout)
                if wait_ms:
                    page.wait_for_timeout(wait_ms)
                meta = _page_meta(page)
                ch = detect_page_challenge(page)
                return {"ok": True, "action": "reload", "challenge": ch, **meta}

            if action == "goto":
                if not url.startswith("http"):
                    return {"ok": False, "error": "goto requires url: https://..."}
                page.goto(url, wait_until=wait_until, timeout=timeout)
                if wait_ms:
                    page.wait_for_timeout(wait_ms)
                meta = _page_meta(page)
                ch = detect_page_challenge(page)
                return {
                    "ok": True,
                    "action": "goto",
                    "challenge": ch,
                    "blocked": ch.get("blocked"),
                    **meta,
                }

            if action == "wait":
                page.wait_for_timeout(max(0, wait_ms))
                if selector and selector != "body":
                    try:
                        page.wait_for_selector(selector, timeout=timeout)
                    except Exception:  # noqa: BLE001
                        pass
                return {"ok": True, "action": "wait", **_page_meta(page)}

            if action == "click":
                target.click(selector, timeout=timeout)
                if wait_ms:
                    page.wait_for_timeout(wait_ms)
                return {
                    "ok": True,
                    "action": "click",
                    "selector": selector,
                    "frame": cmd.get("frame") or "",
                    **_page_meta(page),
                }

            if action in ("fill", "type"):
                value = cmd.get("value") or cmd.get("text") or ""
                if action == "fill":
                    target.fill(selector, value, timeout=timeout)
                else:
                    target.click(selector, timeout=timeout)
                    page.keyboard.type(value, delay=20)
                if wait_ms:
                    page.wait_for_timeout(min(wait_ms, 1000))
                return {
                    "ok": True,
                    "action": action,
                    "selector": selector,
                    "value_len": len(value),
                    "frame": cmd.get("frame") or "",
                    **_page_meta(page),
                }

            if action == "press":
                key = (cmd.get("key") or "Enter").strip()
                if selector and selector != "body":
                    target.press(selector, key, timeout=timeout)
                else:
                    page.keyboard.press(key)
                if wait_ms:
                    page.wait_for_timeout(wait_ms)
                return {"ok": True, "action": "press", "key": key, **_page_meta(page)}

            if action == "scroll":
                dx = int(cmd.get("dx") or 0)
                dy = int(cmd.get("dy") or 600)
                page.mouse.wheel(dx, dy)
                if wait_ms:
                    page.wait_for_timeout(min(wait_ms, 800))
                return {"ok": True, "action": "scroll", "dx": dx, "dy": dy, **_page_meta(page)}

            if action == "text":
                # If URL given and different page, navigate first
                if url.startswith("http") and (not page.url or url.split("#")[0] not in (page.url or "")):
                    page.goto(url, wait_until="domcontentloaded", timeout=timeout)
                    if wait_ms:
                        page.wait_for_timeout(wait_ms)
                    target = _resolve_target(page, cmd)
                try:
                    text = target.inner_text(selector, timeout=timeout)
                except Exception:
                    text = target.inner_text("body", timeout=timeout)
                meta = _page_meta(page)
                return {
                    "ok": True,
                    "action": "text",
                    **meta,
                    "text": (text or "")[:60000],
                    "chars": len(text or ""),
                }

            if action in ("frames", "list_frames"):
                frames = []
                for fr in page.frames:
                    frames.append(
                        {
                            "name": fr.name or "",
                            "url": (fr.url or "")[:300],
                            "is_main": fr == page.main_frame,
                        }
                    )
                return {
                    "ok": True,
                    "action": "frames",
                    "count": len(frames),
                    "frames": frames,
                    **_page_meta(page),
                }

            if action in ("save_image", "download_image", "capture_image"):
                # Save image by CSS selector (img) or by url=...
                img_url = url
                if not img_url.startswith("http") and not img_url.startswith("blob:"):
                    try:
                        img_url = target.eval_on_selector(
                            selector if selector != "body" else "img",
                            "el => el.currentSrc || el.src || ''",
                        )
                    except Exception as e:  # noqa: BLE001
                        return {
                            "ok": False,
                            "action": "save_image",
                            "error": f"Could not resolve image: {e}",
                            **_page_meta(page),
                        }
                if not img_url:
                    return {
                        "ok": False,
                        "action": "save_image",
                        "error": "No image src found",
                        **_page_meta(page),
                    }
                dest = browser_shots_dir() / f"{uuid.uuid4().hex[:12]}_img.png"
                try:
                    if str(img_url).startswith("data:"):
                        import base64
                        import re as _re

                        m = _re.match(
                            r"data:image/[^;]+;base64,(.+)", str(img_url), _re.I | _re.S
                        )
                        if not m:
                            return {"ok": False, "error": "Unsupported data URL", "action": "save_image"}
                        dest.write_bytes(base64.b64decode(m.group(1)))
                    elif str(img_url).startswith("blob:"):
                        # Fetch blob bytes inside page context
                        b64 = target.evaluate(
                            """async (src) => {
                              const r = await fetch(src);
                              const buf = await r.arrayBuffer();
                              const bytes = new Uint8Array(buf);
                              let binary = '';
                              for (let i = 0; i < bytes.length; i++) binary += String.fromCharCode(bytes[i]);
                              return btoa(binary);
                            }""",
                            img_url,
                        )
                        import base64

                        dest.write_bytes(base64.b64decode(b64))
                    else:
                        resp = sess["context"].request.get(str(img_url), timeout=timeout)
                        body = resp.body()
                        # pick extension from content-type
                        ct = (resp.headers.get("content-type") or "").lower()
                        if "jpeg" in ct or "jpg" in ct:
                            dest = dest.with_suffix(".jpg")
                        elif "webp" in ct:
                            dest = dest.with_suffix(".webp")
                        elif "gif" in ct:
                            dest = dest.with_suffix(".gif")
                        dest.write_bytes(body)
                    return {
                        "ok": True,
                        "action": "save_image",
                        "path": str(dest.resolve()),
                        "src": str(img_url)[:300],
                        "bytes": dest.stat().st_size,
                        **_page_meta(page),
                    }
                except Exception as e:  # noqa: BLE001
                    return {
                        "ok": False,
                        "action": "save_image",
                        "error": str(e),
                        "src": str(img_url)[:300],
                        **_page_meta(page),
                    }

            if action == "screenshot_element":
                dest = browser_shots_dir() / f"{uuid.uuid4().hex[:12]}_el.png"
                try:
                    loc = target.locator(selector).first
                    loc.screenshot(path=str(dest), timeout=timeout)
                    return {
                        "ok": True,
                        "action": "screenshot_element",
                        "path": str(dest.resolve()),
                        "selector": selector,
                        **_page_meta(page),
                    }
                except Exception as e:  # noqa: BLE001
                    return {
                        "ok": False,
                        "action": "screenshot_element",
                        "error": str(e),
                        **_page_meta(page),
                    }

            if action == "listen_start":
                buf: list[dict[str, Any]] = sess.setdefault("image_responses", [])

                def _on_response(resp: Any) -> None:
                    try:
                        ct = (resp.headers.get("content-type") or "").lower()
                        u = resp.url or ""
                        if "image/" not in ct and not any(
                            u.lower().split("?")[0].endswith(ext)
                            for ext in (".png", ".jpg", ".jpeg", ".webp", ".gif")
                        ):
                            return
                        if resp.status and int(resp.status) >= 400:
                            return
                        body = resp.body()
                        if len(body) < 2000:
                            return
                        dest = browser_shots_dir() / f"{uuid.uuid4().hex[:12]}_cap.png"
                        if "jpeg" in ct or u.lower().endswith((".jpg", ".jpeg")):
                            dest = dest.with_suffix(".jpg")
                        elif "webp" in ct:
                            dest = dest.with_suffix(".webp")
                        dest.write_bytes(body)
                        buf.append(
                            {
                                "path": str(dest.resolve()),
                                "url": u[:300],
                                "bytes": len(body),
                                "content_type": ct,
                            }
                        )
                    except Exception:  # noqa: BLE001
                        pass

                if not sess.get("_image_listener"):
                    page.on("response", _on_response)
                    sess["_image_listener"] = True
                return {
                    "ok": True,
                    "action": "listen_start",
                    "count": len(buf),
                    **_page_meta(page),
                }

            if action == "listen_images":
                buf = list(sess.get("image_responses") or [])
                return {
                    "ok": True,
                    "action": "listen_images",
                    "count": len(buf),
                    "images": buf[-20:],
                    "latest": buf[-1] if buf else None,
                    **_page_meta(page),
                }

            if action in ("html", "content"):
                if url.startswith("http"):
                    page.goto(url, wait_until="domcontentloaded", timeout=timeout)
                    if wait_ms:
                        page.wait_for_timeout(wait_ms)
                html = page.content()
                return {
                    "ok": True,
                    "action": "html",
                    **_page_meta(page),
                    "html": (html or "")[:100000],
                }

            if action == "screenshot":
                if url.startswith("http"):
                    page.goto(url, wait_until="domcontentloaded", timeout=timeout)
                    if wait_ms:
                        page.wait_for_timeout(wait_ms)
                dest = browser_shots_dir() / f"{uuid.uuid4().hex[:12]}_shot.png"
                page.screenshot(path=str(dest), full_page=full_page)
                return {
                    "ok": True,
                    "action": "screenshot",
                    **_page_meta(page),
                    "path": str(dest.resolve()),
                }

            if action == "pdf":
                if url.startswith("http"):
                    page.goto(url, wait_until="domcontentloaded", timeout=timeout)
                dest = browser_shots_dir() / f"{uuid.uuid4().hex[:12]}.pdf"
                page.pdf(path=str(dest))
                return {"ok": True, "action": "pdf", "path": str(dest.resolve()), **_page_meta(page)}

            if action == "links":
                n = max(1, min(80, int(cmd.get("n") or 30)))
                hrefs = page.eval_on_selector_all(
                    "a[href]",
                    """els => els.map(a => ({text: (a.innerText||'').trim().slice(0,120),
                        href: a.href})).filter(x => x.href && x.href.startsWith('http'))""",
                )
                # dedupe
                seen = set()
                links = []
                for h in hrefs or []:
                    u = h.get("href") or ""
                    if u in seen:
                        continue
                    seen.add(u)
                    links.append(h)
                    if len(links) >= n:
                        break
                return {"ok": True, "action": "links", "count": len(links), "links": links, **_page_meta(page)}

            if action == "evaluate":
                script = cmd.get("script") or cmd.get("value") or "document.title"
                # allow expression or function body; honour frame target
                try:
                    result = target.evaluate(script)
                except Exception:
                    try:
                        result = target.evaluate(f"() => ({script})")
                    except Exception:
                        result = page.evaluate(script)
                return {
                    "ok": True,
                    "action": "evaluate",
                    "result": result if not isinstance(result, (dict, list)) else str(result)[:8000],
                    "frame": cmd.get("frame") or "",
                    **_page_meta(page),
                }

            if action == "download":
                # Download URL via browser context request or page
                if not url.startswith("http"):
                    return {"ok": False, "error": "download requires url"}
                dest = browser_downloads_dir() / f"{uuid.uuid4().hex[:10]}_{Path(url.split('?')[0]).name or 'file'}"
                # sanitize name
                if not dest.suffix:
                    dest = dest.with_suffix(".bin")
                try:
                    resp = sess["context"].request.get(url, timeout=timeout)
                    dest.write_bytes(resp.body())
                    return {
                        "ok": True,
                        "action": "download",
                        "url": url,
                        "path": str(dest.resolve()),
                        "bytes": dest.stat().st_size,
                        "status": resp.status,
                    }
                except Exception as e:  # noqa: BLE001
                    return {"ok": False, "action": "download", "error": str(e), "url": url}

            return {"ok": False, "error": f"Unknown action: {action}"}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "action": action, "error": str(e), **_page_meta(page)}


def run_browser(
    *,
    action: str = "goto",
    url: str = "",
    selector: str = "body",
    full_page: str = "false",
    wait_ms: str = "1500",
    wait_until: str = "",
    value: str = "",
    text: str = "",
    key: str = "",
    script: str = "",
    dx: str = "0",
    dy: str = "600",
    n: str = "30",
    timeout: str = "60000",
    headed: str = "",
    frame: str = "",
    auto_headed: str = "true",
    wait_captcha: str = "false",
    **extra: Any,
) -> dict[str, Any]:
    """
    Run a browser action on the persistent session.

    auto_headed: if true (default), when headless hits captcha/anti-bot after
      goto/reload, automatically reopen as headed with the same profile.
    wait_captcha: if true after a block, wait for the user to clear the captcha.
    """
    action = (action or "goto").lower().strip()
    auto_h = _bool(auto_headed if auto_headed != "" else extra.get("auto_headed", "true"), True)
    wait_cap = _bool(wait_captcha if wait_captcha != "" else extra.get("wait_captcha", "false"), False)

    # Special actions that manage session themselves (avoid nested lock issues)
    if action in ("switch_headed", "headed_fallback"):
        try:
            return switch_to_headed(reason=str(extra.get("reason") or "manual"), reload_url=url)
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "action": "switch_headed", "error": str(e)}

    if action in ("wait_for_captcha", "wait_captcha"):
        try:
            to = int(timeout or 180000)
        except Exception:  # noqa: BLE001
            to = 180000
        try:
            return wait_for_captcha_clear(timeout_ms=to)
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "action": "wait_for_captcha", "error": str(e)}

    # Actions that need a URL when session has no page yet
    needs_url = action in ("goto", "download")
    if needs_url and not (url or "").startswith("http"):
        if action == "goto":
            return {"ok": False, "error": "url must start with http:// or https://"}

    # Force headed session if requested
    headed_override = None
    if headed not in (None, ""):
        headed_override = _bool(headed)

    cmd = {
        "action": action,
        "url": url,
        "selector": selector,
        "full_page": full_page,
        "wait_ms": wait_ms,
        "wait_until": wait_until or extra.get("wait_until") or "",
        "frame": frame or extra.get("frame") or extra.get("iframe") or "",
        "value": value or text or extra.get("value") or "",
        "text": text,
        "key": key,
        "script": script or extra.get("script") or "",
        "dx": dx,
        "dy": dy,
        "n": n,
        "timeout": timeout,
        "headed": headed if headed_override is None else ("true" if headed_override else "false"),
        "url_glob": extra.get("url_glob") or extra.get("pattern") or "",
        "click_selector": extra.get("click_selector") or "",
    }
    try:
        # Ensure session mode before action if headed override
        if headed_override is not None:
            with _session_lock:
                if not _session or _session.get("headed") != headed_override:
                    _close_session_unlocked()
                    _ensure_session(headed=headed_override)

        result = _run_session_action(cmd)

        # Auto headless → headed when blocked
        if (
            auto_h
            and action in ("goto", "reload", "detect_challenge")
            and isinstance(result, dict)
            and result.get("ok")
        ):
            ch = result.get("challenge") or {}
            blocked = bool(result.get("blocked") or ch.get("blocked"))
            currently_headed = bool(_session and _session.get("headed"))
            if blocked and not currently_headed:
                reason = f"{ch.get('kind') or 'challenge'}: {', '.join(ch.get('evidence') or [])[:120]}"
                fb = switch_to_headed(
                    reason=reason,
                    reload_url=url if (url or "").startswith("http") else str(result.get("url") or ""),
                )
                result = {
                    **result,
                    "auto_headed_fallback": True,
                    "headed_switch": fb,
                    "headed": True,
                    "message": (
                        "Page blocked in headless; switched to visible Chrome. "
                        + str(fb.get("message") or "")
                    ),
                }
                if wait_cap or ch.get("kind") == "captcha":
                    wait_res = wait_for_captcha_clear(
                        timeout_ms=int(timeout or 180000) if str(timeout).isdigit() else 180000
                    )
                    result["captcha_wait"] = wait_res
                    result["challenge"] = wait_res.get("challenge") or result.get("challenge")
                    result["blocked"] = bool(
                        (wait_res.get("challenge") or {}).get("blocked")
                    )
                elif action == "goto" and (url or "").startswith("http"):
                    # Re-check after headed reload
                    recheck = _run_session_action(
                        {
                            "action": "detect_challenge",
                            "url": "",
                            "selector": "body",
                            "wait_ms": "500",
                            "timeout": timeout,
                        }
                    )
                    result["challenge"] = recheck.get("challenge") or result.get("challenge")
                    result["blocked"] = recheck.get("blocked")

        # Explicit wait_captcha after any action
        if wait_cap and isinstance(result, dict):
            ch = result.get("challenge") or detect_page_challenge()
            if ch.get("blocked"):
                if not (_session and _session.get("headed")):
                    switch_to_headed(reason="wait_captcha", reload_url=str(result.get("url") or url or ""))
                wr = wait_for_captcha_clear(
                    timeout_ms=int(timeout) if str(timeout).isdigit() else 180000
                )
                result["captcha_wait"] = wr

        return result
    except ImportError as e:
        return {
            "ok": False,
            "error": (
                "Playwright not installed. Run Launch.bat or: "
                "pip install playwright && python -m playwright install chromium\n"
                f"Details: {e}"
            ),
        }
    except Exception as e:  # noqa: BLE001
        # fallback one-shot selenium for basic actions only
        if action in ("goto", "text", "screenshot", "html") and (url or "").startswith("http"):
            try:
                return _run_selenium(action, url, selector=selector, full_page=full_page, wait_ms=wait_ms)
            except Exception as e2:  # noqa: BLE001
                return {"ok": False, "error": f"{e}; selenium fallback: {e2}"}
        return {"ok": False, "error": str(e)}


def _run_selenium(action: str, url: str, **kwargs: Any) -> dict[str, Any]:
    from selenium import webdriver  # type: ignore
    from selenium.webdriver.chrome.options import Options  # type: ignore
    from selenium.webdriver.common.by import By  # type: ignore

    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--window-size=1280,800")
    opts.add_argument("--no-sandbox")
    driver = webdriver.Chrome(options=opts)
    try:
        driver.set_page_load_timeout(60)
        driver.get(url)
        if action == "goto":
            return {"ok": True, "action": "goto", "url": driver.current_url, "title": driver.title}
        if action == "screenshot":
            dest = browser_shots_dir() / f"{uuid.uuid4().hex[:12]}_shot.png"
            driver.save_screenshot(str(dest))
            return {
                "ok": True,
                "action": "screenshot",
                "url": driver.current_url,
                "title": driver.title,
                "path": str(dest.resolve()),
            }
        if action == "text":
            sel = kwargs.get("selector") or "body"
            try:
                el = driver.find_element(By.CSS_SELECTOR, sel)
                text = el.text
            except Exception:
                text = driver.find_element(By.TAG_NAME, "body").text
            return {
                "ok": True,
                "action": "text",
                "url": driver.current_url,
                "title": driver.title,
                "text": (text or "")[:50000],
            }
        if action == "html":
            return {
                "ok": True,
                "action": "html",
                "url": driver.current_url,
                "title": driver.title,
                "html": (driver.page_source or "")[:80000],
            }
        return {"ok": False, "error": f"Unknown action: {action}"}
    finally:
        driver.quit()


def browser_available() -> dict[str, Any]:
    ensure_playwright_env()
    has_pw = False
    has_se = False
    try:
        import playwright  # noqa: F401

        has_pw = True
    except ImportError:
        pass
    try:
        import selenium  # noqa: F401

        has_se = True
    except ImportError:
        pass
    chrome = bool(shutil.which("chrome") or shutil.which("chromium") or shutil.which("msedge"))
    return {
        "playwright": has_pw,
        "selenium": has_se,
        "chrome_in_path": chrome,
        "chromium_portable": _chromium_installed(),
        "browsers_path": str(browsers_dir().resolve()),
        "session_open": bool(_session and _session.get("page")),
        "profile_dir": str(browser_profile_dir().resolve()),
    }
