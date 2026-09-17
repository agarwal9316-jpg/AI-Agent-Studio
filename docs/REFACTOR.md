# Refactor Plan — AI Agent Studio

**Goal:** Make the codebase maintainable without breaking the running Windows GUI.

**Current critical problem:**  
`app/ui/app_window.py` = **20,438 lines / 409 methods** in a single class.  
This is the #1 blocker for safe future work.

---

## Priority 1 — Split the God Class (must do first)

Target structure after split:

```
app/ui/
  app_window.py          # thin shell only (< 800 lines)
  pages/
    chat_page.py         # extract all _chat_* methods + chat UI
    home_page.py
    settings_page.py
    knowledge_page.py
    ...
  components/            # already exists — expand it
  navigation.py          # sidebar + page switching
  status_bar.py
  system_monitor.py
```

### Recommended extraction order
1. Chat page (largest and most used)
2. System monitor bar
3. Sidebar / navigation
4. Remaining pages that are still inside `app_window.py`

**Rule:** Never leave a method in `AppWindow` that only belongs to one page.

---

## Priority 2 — Break remaining large page files

| File                    | Current lines | Target          |
|-------------------------|---------------|-----------------|
| org_page.py             | 2,553         | < 900           |
| team_page.py            | 1,741         | < 800           |
| org_chart_view.py       | 1,160         | < 700           |
| mgmt_pages.py           | 991           | < 600           |

Split into view + controller + dialogs.

---

## Priority 3 — Clean temporary scripts (done in this branch)

Deleted root-level one-off scripts that contained hardcoded local Windows paths:
- fix_*.py
- check_*.py
- find_naming.py
- browser.py (old PyQt experiment)
- test_run.py

These should never have been committed.

---

## Priority 4 — Tests

Current tests are mostly roadmap/pending-task checks.  
Needed next:
- Unit tests for `app/core/services/chat`, LLM, tools, RAG
- Smoke tests for page construction (even if limited under CustomTkinter)

---

## Priority 5 — Long-term UI decision

CustomTkinter is acceptable for the portable Windows goal **today**.  
If the project continues to grow past ~100k lines of UI code, evaluate:
- PySide6 / Qt (better performance & tooling)
- or a web frontend + local backend later

Do **not** migrate now. Finish the split first.

---

## How to work on the split safely

1. Create a feature branch for each major extraction.
2. Extract one logical group of methods at a time.
3. Keep the app launchable after every small commit.
4. Test on real Windows after each extraction.
5. Prefer composition over inheritance.

---

**Status of this branch:** Cleanup + plan only.  
Next recommended action: start extracting the Chat page into `app/ui/pages/chat_page.py`.
