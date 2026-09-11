"""Read the ALREADY OPEN 'Grok - Google Chrome' window via UI Automation.

Does not need remote debugging. Uses the user's real logged-in Chrome window.
"""
from __future__ import annotations

from pathlib import Path

import uiautomation as auto

OUT = Path(__file__).resolve().parents[1] / "data"
OUT.mkdir(parents=True, exist_ok=True)


def find_grok_window():
    root = auto.GetRootControl()
    for w in root.GetChildren():
        name = w.Name or ""
        if "Grok" in name and "Chrome" in name:
            return w
    for w in root.GetChildren():
        name = w.Name or ""
        if "Grok" in name:
            return w
    return None


def walk(ctrl, depth: int, max_depth: int, items: list, max_kids: int = 100) -> None:
    if depth > max_depth:
        return
    try:
        nm = (ctrl.Name or "").strip()
        ct = ctrl.ControlTypeName
        if nm and len(nm) < 200:
            items.append((depth, ct, nm))
        kids = ctrl.GetChildren()
        for k in kids[:max_kids]:
            walk(k, depth + 1, max_depth, items, max_kids)
    except Exception:
        return


def main() -> None:
    win = find_grok_window()
    if not win:
        print("NO_GROK_WINDOW")
        print("Open Chrome with Grok visible (title should contain 'Grok').")
        return
    print("WINDOW:", win.Name)
    print("CLASS:", win.ClassName)
    try:
        win.SetFocus()
    except Exception as e:
        print("focus warn", e)

    items: list[tuple[int, str, str]] = []
    walk(win, 0, 14, items)

    # Prefer interactive-ish types
    want = {
        "ButtonControl",
        "EditControl",
        "TextControl",
        "MenuItemControl",
        "ListItemControl",
        "HyperlinkControl",
        "ComboBoxControl",
        "TabItemControl",
        "CheckBoxControl",
        "RadioButtonControl",
        "SplitButtonControl",
        "ToolBarControl",
        "TreeItemControl",
        "DocumentControl",
    }
    seen: set[tuple[str, str]] = set()
    lines: list[str] = []
    for depth, ct, nm in items:
        key = (ct, nm)
        if key in seen:
            continue
        seen.add(key)
        if ct in want or depth <= 2:
            pad = "  " * min(depth, 8)
            lines.append(f"{pad}{ct}: {nm}")

    text = "\n".join(lines)
    out_path = OUT / "grok_live_uia.txt"
    out_path.write_text(text, encoding="utf-8")
    print("--- CONTROLS (unique) ---")
    print("\n".join(lines[:250]))
    print("TOTAL_LINES", len(lines))
    print("SAVED", out_path)

    # Buttons only summary
    buttons = [nm for _, ct, nm in items if ct == "ButtonControl"]
    uniq_btn = []
    s = set()
    for b in buttons:
        if b not in s:
            s.add(b)
            uniq_btn.append(b)
    print("--- BUTTONS ---")
    for b in uniq_btn[:80]:
        print(" *", b)


if __name__ == "__main__":
    main()
