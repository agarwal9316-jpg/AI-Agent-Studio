"""
Headless Perchance AI text-to-image generator automation.

Site: https://perchance.org/ai-text-to-image-generator

Notes:
  - UI is in iframe #outputIframeEl; images render in nested
    image-generation.perchance.org embeds.
  - Site uses anti-bot verification that often fails under pure headless
    automation (VPN / automation signals). On failure we surface a clear error
    and optionally retry with a visible (headed) browser + persistent profile.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any, Callable

from app.core.services.web.browser_tool import (
    close_browser_session,
    detect_page_challenge,
    run_browser,
    switch_to_headed,
    wait_for_captcha_clear,
)

PERCHANCE_URL = "https://perchance.org/ai-text-to-image-generator"
FRAME = "outputIframeEl"
IMG_FRAME = "image-generation.perchance.org"

ProgressCb = Callable[[str], None]


def _prog(cb: ProgressCb | None, msg: str) -> None:
    if cb:
        try:
            cb(msg)
        except Exception:  # noqa: BLE001
            pass


def _file_ok(path: str | None, min_bytes: int = 8000) -> bool:
    if not path:
        return False
    p = Path(str(path))
    try:
        return p.is_file() and p.stat().st_size >= min_bytes
    except Exception:  # noqa: BLE001
        return False


def _save_data_url(data_url: str) -> str | None:
    import base64
    import uuid

    from app.core.services.web.browser_tool import browser_shots_dir

    m = re.match(r"data:image/([^;]+);base64,(.+)", data_url or "", re.I | re.S)
    if not m:
        return None
    ext = m.group(1).split("+")[0].lower()
    if ext == "jpeg":
        ext = "jpg"
    if ext not in ("png", "jpg", "webp", "gif"):
        ext = "png"
    dest = browser_shots_dir() / f"{uuid.uuid4().hex[:12]}_data.{ext}"
    try:
        dest.write_bytes(base64.b64decode(m.group(2)))
        if dest.stat().st_size < 1000:
            return None
        return str(dest.resolve())
    except Exception:  # noqa: BLE001
        return None


def _run_once(
    prompt: str,
    *,
    headed: bool,
    timeout_s: float,
    on_progress: ProgressCb | None,
) -> dict[str, Any]:
    steps: list[str] = []
    anti_bot = False
    headed_s = "true" if headed else "false"
    mode = "headed" if headed else "headless"

    def note(msg: str) -> None:
        steps.append(msg)
        _prog(on_progress, msg)

    note(f"Opening Perchance ({mode})…")
    close_browser_session()  # ensure clean session / correct headed flag
    r = run_browser(
        action="goto",
        url=PERCHANCE_URL,
        wait_until="networkidle",
        wait_ms="8000",
        headed=headed_s,
        timeout="90000",
        auto_headed="true" if not headed else "false",
        wait_captcha="false",
    )
    if not r.get("ok"):
        return {
            "ok": False,
            "error": f"goto failed: {r.get('error')}",
            "steps": steps,
            "prompt": prompt,
            "anti_bot": False,
        }
    if r.get("auto_headed_fallback"):
        note("Anti-bot/captcha in headless → switched to headed browser")
        headed = True
        mode = "headed"
    note(f"Page loaded: {r.get('title') or r.get('url')}")
    ch0 = r.get("challenge") or detect_page_challenge()
    if ch0.get("blocked") and ch0.get("kind") == "captcha":
        note("Captcha detected — waiting for user to solve in browser window…")
        if not headed:
            switch_to_headed(reason="perchance_captcha", reload_url=PERCHANCE_URL)
            headed = True
            mode = "headed"
        wr = wait_for_captcha_clear(timeout_ms=120_000, on_progress=note)
        if not wr.get("cleared"):
            return {
                "ok": False,
                "error": wr.get("error") or "Captcha not cleared in time",
                "steps": steps,
                "prompt": prompt,
                "anti_bot": True,
            }
    run_browser(action="listen_start")

    for _ in range(25):
        fr = run_browser(action="frames")
        if any("ai-text-to-image" in str(f.get("url") or "") for f in (fr.get("frames") or [])):
            break
        time.sleep(0.4)
    note("Generator iframe ready")

    run_browser(
        action="evaluate",
        frame=FRAME,
        script="""() => {
          const b = [...document.querySelectorAll('button')].find(x => /got it/i.test(x.innerText||''));
          if (b) b.click();
          return true;
        }""",
        wait_ms="400",
    )

    pj = json.dumps(prompt)
    fill = run_browser(
        action="evaluate",
        frame=FRAME,
        script=f"""() => {{
          const areas = [...document.querySelectorAll('textarea')];
          if (!areas.length) return {{ok:false, err:'no textarea'}};
          const isNotes = (t) => /store prompts|notes/i.test(t.placeholder||'');
          let el = areas.find(t => !isNotes(t));
          if (!el) el = areas[Math.min(1, areas.length-1)];
          const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set;
          el.focus();
          setter.call(el, {pj});
          for (const ev of ['input','change','keyup']) el.dispatchEvent(new Event(ev, {{bubbles:true}}));
          return {{ok:true, ph:(el.placeholder||'').slice(0,50), len: el.value.length}};
        }}""",
        wait_ms="600",
    )
    note(f"Fill description: {fill.get('result')}")
    if "no textarea" in str(fill.get("result") or "") or (
        isinstance(fill.get("result"), dict) and not fill["result"].get("ok")
    ):
        # still try Playwright fill of second textarea via selector
        run_browser(
            action="fill",
            frame=FRAME,
            selector="textarea",
            value=prompt,
            wait_ms="400",
        )

    note("Clicking generate…")
    run_browser(action="click", frame=FRAME, selector="#generateButtonEl", wait_ms="1500")
    run_browser(
        action="evaluate",
        frame=FRAME,
        script="""() => {
          const b = document.querySelector('#generateButtonEl');
          if (b) b.click();
          return b ? (b.innerText||'').trim() : 'missing';
        }""",
        wait_ms="800",
    )
    note("Generate requested")

    deadline = time.time() + max(45.0, timeout_s)
    saved_path: str | None = None
    poll = 0
    last_embed = ""
    while time.time() < deadline:
        poll += 1
        time.sleep(4 if poll < 6 else 5)

        heard = run_browser(action="listen_images")
        for img in reversed(list(heard.get("images") or [])):
            if isinstance(img, dict) and _file_ok(img.get("path"), 10000):
                saved_path = str(img["path"])
                note(f"Network image captured ({img.get('bytes')} bytes)")
                break
        if saved_path:
            break

        st = run_browser(
            action="evaluate",
            frame=IMG_FRAME,
            script="""() => {
              const body = (document.body && document.body.innerText) || '';
              const imgs = [...document.querySelectorAll('img')].map(i => ({
                src: (i.currentSrc||i.src||'').slice(0,220),
                w: i.naturalWidth||0, h: i.naturalHeight||0
              })).filter(x => x.w >= 64);
              let canvasFull = null;
              for (const c of document.querySelectorAll('canvas')) {
                if (c.width >= 64 && c.height >= 64) {
                  try { canvasFull = c.toDataURL('image/png'); break; } catch (e) {}
                }
              }
              return {
                body: body.slice(0,160),
                starting: /starting/i.test(body),
                antiBot: /anti-bot|verification failed|vpn/i.test(body),
                imgs,
                canvasFull
              };
            }""",
        )
        raw = st.get("result")
        data: dict[str, Any] = {}
        if isinstance(raw, dict):
            data = raw
        elif isinstance(raw, str) and raw.startswith("{"):
            try:
                import ast

                data = ast.literal_eval(raw)
            except Exception:  # noqa: BLE001
                data = {}

        last_embed = str(data.get("body") or "")
        if data.get("antiBot") or "anti-bot" in last_embed.lower() or "verification failed" in last_embed.lower():
            anti_bot = True
            note(f"Anti-bot detected: {last_embed[:80]}")
            # Mid-run headed fallback + optional captcha wait (once)
            if not headed and poll <= 4:
                note("Switching to headed browser to tackle anti-bot…")
                switch_to_headed(reason="perchance_anti_bot", reload_url=PERCHANCE_URL)
                headed = True
                mode = "headed"
                # re-fill and re-click generate after headed reload
                run_browser(action="listen_start")
                run_browser(
                    action="evaluate",
                    frame=FRAME,
                    script=f"""() => {{
                      const areas = [...document.querySelectorAll('textarea')];
                      const isNotes = (t) => /store prompts|notes/i.test(t.placeholder||'');
                      let el = areas.find(t => !isNotes(t)) || areas[1] || areas[0];
                      if (!el) return false;
                      const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set;
                      setter.call(el, {pj});
                      el.dispatchEvent(new Event('input', {{bubbles:true}}));
                      return true;
                    }}""",
                )
                run_browser(action="click", frame=FRAME, selector="#generateButtonEl", wait_ms="1500")
                note("Re-submitted generate in headed mode")

        note(f"Poll {poll}: embed={last_embed[:50]!r}")

        if data.get("canvasFull"):
            p = _save_data_url(str(data["canvasFull"]))
            if p:
                saved_path = p
                note(f"Saved canvas: {p}")
                break

        for im in data.get("imgs") or []:
            if not isinstance(im, dict):
                continue
            src = str(im.get("src") or "")
            if src.startswith("data:"):
                p = _save_data_url(src)
            elif src.startswith("http") or src.startswith("blob:"):
                sav = run_browser(
                    action="save_image",
                    frame=IMG_FRAME,
                    url=src if src.startswith("http") else "",
                    selector="img",
                )
                p = sav.get("path") if sav.get("ok") else None
            else:
                p = None
            if _file_ok(p, 5000):
                saved_path = str(p)
                note(f"Saved embed image: {saved_path}")
                break
        if saved_path:
            break

        # When generation finished (not Starting / not anti-bot), screenshot embed tile
        if not data.get("starting") and not data.get("antiBot") and poll >= 3 and last_embed:
            el = run_browser(
                action="screenshot_element",
                frame=FRAME,
                selector="iframe.text-to-image-plugin-image-iframe, iframe[src*='image-generation'], .t2i-image-ctn",
            )
            if el.get("ok") and _file_ok(el.get("path"), 15000):
                saved_path = str(el["path"])
                note(f"Screenshot nested embed: {saved_path}")
                break

        # stop early if anti-bot keeps failing
        if anti_bot and poll >= 8:
            note("Stopping early due to repeated anti-bot failures")
            break

    shot = run_browser(action="screenshot", full_page="false", wait_ms="200")
    shot_path = shot.get("path") if shot.get("ok") else None

    # Do NOT treat pure "Starting..." spinner screenshots as success
    if not saved_path and anti_bot:
        close_browser_session()
        return {
            "ok": False,
            "error": (
                "Perchance anti-bot verification failed in automated browser. "
                "Tips: turn off VPN; Settings → enable browser headed mode; "
                "open the site once manually in headed browser to pass checks; "
                "or use <<<IMAGE_GEN>>> with an image-capable API model."
            ),
            "prompt": prompt,
            "steps": steps,
            "anti_bot": True,
            "screenshot": shot_path,
            "embed_status": last_embed,
        }

    if not saved_path:
        el = run_browser(action="screenshot_element", selector="#outputIframeEl")
        if el.get("ok") and _file_ok(el.get("path"), 20000):
            # only accept large screenshots that likely include content
            saved_path = str(el["path"])
            note("Fallback: generator iframe screenshot")
        elif shot_path and _file_ok(shot_path, 20000):
            saved_path = shot_path
            note("Fallback: page screenshot")

    close_browser_session()

    if not saved_path:
        return {
            "ok": False,
            "error": "Timed out waiting for a generated image from Perchance",
            "prompt": prompt,
            "steps": steps,
            "anti_bot": anti_bot,
            "screenshot": shot_path,
            "embed_status": last_embed,
        }

    return {
        "ok": True,
        "path": saved_path,
        "screenshot": shot_path,
        "prompt": prompt,
        "steps": steps,
        "anti_bot": anti_bot,
        "url": PERCHANCE_URL,
        "mode": mode,
    }


def generate_image_via_perchance(
    prompt: str,
    *,
    timeout_s: float = 120.0,
    headed: bool = False,
    keep_session: bool = False,  # noqa: ARG001 — kept for API compatibility
    on_progress: ProgressCb | None = None,
    auto_headed_retry: bool = True,
) -> dict[str, Any]:
    """
    Generate via Perchance. Headless first (unless headed=True).
    On anti-bot failure, optionally retry once with a visible browser window.
    """
    prompt = (prompt or "").strip()
    if not prompt:
        return {"ok": False, "error": "Empty prompt"}

    # Config override: browser_headed in settings
    if not headed:
        try:
            from app.core.services.data.storage import load_config

            headed = bool(load_config().get("browser_headed", False))
        except Exception:  # noqa: BLE001
            pass

    res = _run_once(prompt, headed=headed, timeout_s=timeout_s, on_progress=on_progress)
    if res.get("ok"):
        return res

    if (
        auto_headed_retry
        and not headed
        and res.get("anti_bot")
    ):
        _prog(on_progress, "Anti-bot failed headless — retrying with visible browser…")
        res2 = _run_once(
            prompt,
            headed=True,
            timeout_s=timeout_s,
            on_progress=on_progress,
        )
        res2["retried_headed"] = True
        res2["first_error"] = res.get("error")
        return res2

    return res


def tool_instructions() -> str:
    return """
## Perchance free AI image generator (browser)

Generate an image via https://perchance.org/ai-text-to-image-generator without a paid image API:

<<<PERCHANCE_IMAGE>>>
a cute orange cat with sunglasses, digital art
<<<END_PERCHANCE_IMAGE>>>

Uses portable Chromium (headless by default). The site may run anti-bot checks;
if they fail, the tool retries with a visible browser window, or you can enable
**Settings → browser headed**. Result image is attached in chat when generation succeeds.

Prefer <<<IMAGE_GEN>>> when you have an OpenAI/OpenRouter image model configured.
""".strip()


PERCHANCE_RE = re.compile(
    r"<<<PERCHANCE_IMAGE>>>\s*(.*?)\s*<<<END_PERCHANCE_IMAGE>>>",
    re.DOTALL | re.IGNORECASE,
)


def extract_perchance_blocks(text: str) -> list[str]:
    return [m.group(1).strip() for m in PERCHANCE_RE.finditer(text or "") if m.group(1).strip()]
