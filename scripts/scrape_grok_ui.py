"""Launch Chrome with user Grok profile + scrape grok.com UI controls."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data"
OUT.mkdir(parents=True, exist_ok=True)

CHROME = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")
SRC = Path(os.environ["LOCALAPPDATA"]) / "Google" / "Chrome" / "User Data"
DST = Path(os.environ["LOCALAPPDATA"]) / "Google" / "Chrome" / "GrokCDP"
PORT = 9333


def ensure_profile() -> None:
    DST.mkdir(parents=True, exist_ok=True)
    local_state = SRC / "Local State"
    if local_state.exists():
        shutil.copy2(local_state, DST / "Local State")
    default_src = SRC / "Default"
    default_dst = DST / "Default"
    default_dst.mkdir(parents=True, exist_ok=True)
    for name in (
        "Cookies",
        "Login Data",
        "Preferences",
        "Secure Preferences",
        "Web Data",
        "Bookmarks",
        "History",
    ):
        p = default_src / name
        if p.exists():
            try:
                shutil.copy2(p, default_dst / name)
            except Exception:
                pass
    net_src = default_src / "Network"
    net_dst = default_dst / "Network"
    if net_src.exists():
        net_dst.mkdir(parents=True, exist_ok=True)
        for p in net_src.iterdir():
            if p.is_file():
                try:
                    shutil.copy2(p, net_dst / p.name)
                except Exception:
                    pass


def kill_chrome() -> None:
    subprocess.run(
        ["taskkill", "/F", "/IM", "chrome.exe"],
        capture_output=True,
        text=True,
    )
    time.sleep(2)


def wait_cdp(timeout: float = 20.0) -> bool:
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/version", timeout=1)
            return True
        except Exception:
            time.sleep(0.5)
    return False


def main() -> None:
    kill_chrome()
    ensure_profile()
    args = [
        str(CHROME),
        f"--remote-debugging-port={PORT}",
        "--remote-allow-origins=*",
        f"--user-data-dir={DST}",
        "--profile-directory=Default",
        "--no-first-run",
        "--no-default-browser-check",
        "https://grok.com/",
    ]
    proc = subprocess.Popen(args)
    print("chrome pid", proc.pid)
    if not wait_cdp(25):
        raise SystemExit("CDP did not start")

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{PORT}")
        page = None
        for ctx in browser.contexts:
            for pg in ctx.pages:
                print("page:", pg.url[:140])
                if "grok" in (pg.url or "").lower():
                    page = pg
        if page is None:
            page = browser.contexts[0].new_page()
            page.goto("https://grok.com/", timeout=90000)
        page.bring_to_front()
        page.wait_for_timeout(6000)
        page.screenshot(path=str(OUT / "grok_ui_1.png"), full_page=False)
        print("URL", page.url)
        print("TITLE", page.title())

        data = page.evaluate(
            """() => {
          const out = {buttons: [], aria: [], placeholders: [], texts: []};
          const push = (arr, t) => {
            t = (t || '').trim().replace(/\\s+/g, ' ');
            if (t && t.length < 120) arr.push(t);
          };
          document.querySelectorAll('button, [role="button"], a').forEach(el => {
            push(out.buttons, el.innerText || el.getAttribute('aria-label') || el.title);
          });
          document.querySelectorAll('[aria-label]').forEach(el => {
            push(out.aria, el.getAttribute('aria-label'));
          });
          document.querySelectorAll('input, textarea, [contenteditable=true]').forEach(el => {
            push(
              out.placeholders,
              el.getAttribute('placeholder') ||
                el.getAttribute('aria-label') ||
                el.getAttribute('data-placeholder')
            );
          });
          document.querySelectorAll('h1,h2,h3,span,div,p,label').forEach(el => {
            if (el.children.length === 0) push(out.texts, el.innerText);
          });
          out.buttons = [...new Set(out.buttons)].slice(0, 150);
          out.aria = [...new Set(out.aria)].slice(0, 150);
          out.placeholders = [...new Set(out.placeholders)].slice(0, 50);
          out.texts = [...new Set(out.texts)]
            .filter(t => t.length > 1 && t.length < 80)
            .slice(0, 100);
          return out;
        }"""
        )
        print(json.dumps(data, indent=2))
        (OUT / "grok_ui_controls.json").write_text(json.dumps(data, indent=2), encoding="utf-8")

        # Cookie banner
        for name in ("Accept All", "Accept All Cookies", "Allow All"):
            try:
                loc = page.get_by_role("button", name=name)
                if loc.count():
                    loc.first.click(timeout=2500)
                    page.wait_for_timeout(1000)
                    print("cookies:", name)
                    break
            except Exception as e:
                print("cookies skip", e)

        # Settings
        try:
            page.get_by_role("button", name="Settings").first.click(timeout=3000)
            page.wait_for_timeout(2000)
            page.screenshot(path=str(OUT / "grok_settings.png"), full_page=False)
            settings_txt = page.inner_text("body")
            (OUT / "grok_settings.txt").write_text(settings_txt[:15000], encoding="utf-8")
            print("SETTINGS_HEAD", settings_txt[:2000].replace("\n", " | "))
            page.keyboard.press("Escape")
            page.wait_for_timeout(500)
        except Exception as e:
            print("settings fail", e)

        # Model select
        try:
            page.get_by_label("Model select").first.click(timeout=3000)
            page.wait_for_timeout(1500)
            page.screenshot(path=str(OUT / "grok_models.png"), full_page=False)
            print("MODELS", page.inner_text("body")[-2500:].replace("\n", " | "))
            page.keyboard.press("Escape")
        except Exception as e:
            print("models fail", e)

        # Fast control
        try:
            page.get_by_role("button", name="Fast").first.click(timeout=2000)
            page.wait_for_timeout(800)
            page.screenshot(path=str(OUT / "grok_fast.png"), full_page=False)
            print("clicked Fast")
        except Exception as e:
            print("fast fail", e)

        # Imagine
        try:
            page.get_by_role("button", name="Imagine").first.click(timeout=3000)
            page.wait_for_timeout(2500)
            page.screenshot(path=str(OUT / "grok_imagine.png"), full_page=False)
            print("IMAGINE_URL", page.url)
            print("IMAGINE", page.inner_text("body")[:2000].replace("\n", " | "))
        except Exception as e:
            print("imagine fail", e)
            try:
                page.goto("https://grok.com/imagine", timeout=60000)
                page.wait_for_timeout(2500)
                page.screenshot(path=str(OUT / "grok_imagine.png"), full_page=False)
                print("IMAGINE_GOTO", page.inner_text("body")[:2000].replace("\n", " | "))
            except Exception as e2:
                print("imagine goto fail", e2)

        # Home again
        try:
            page.goto("https://grok.com/", timeout=60000)
            page.wait_for_timeout(2000)
        except Exception:
            pass

        body = page.inner_text("body")
        (OUT / "grok_body.txt").write_text(body[:20000], encoding="utf-8")
        print("BODY_LEN", len(body))
        print("BODY_HEAD", body[:2000].replace("\n", " | "))
        page.screenshot(path=str(OUT / "grok_ui_final.png"), full_page=False)
        print("DONE", OUT)
        print("LOGIN?", "Sign in" not in body and "Sign up" not in body)


if __name__ == "__main__":
    main()
