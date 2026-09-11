# Release checklist (docs sync)

Lightweight process enforced by `scripts/check_docs_sync.py`.

## Before tagging / shipping

1. **Bump VERSION trio** (must match):
   - `VERSION`
   - `app/version.py` (`__version__`)
   - `version_manifest.json` (`version` + short `notes`)
2. **CHANGELOG row** — add a `| **X.Y.Z** | … |` line at the top of the 1.7.x table in `docs/CHANGELOG.md`.
3. **Docs touch as needed:**
   - `docs/CONTINUITY.md` — update **Head** + Resume **Last version**
   - `docs/FEATURES.md` — bump `**Version:**` line; add/adjust feature rows
   - `docs/ROADMAP.md` — mark done items; bump Current header
   - Other docs (`UI_MAP`, `DATA_MODEL`, …) only when the change warrants it
4. **Run the checker:**

```bat
python scripts/check_docs_sync.py
```

Must exit 0. Automated coverage: `python tests/test_roadmap_docs_sync.py`.

## What the checker verifies

| Check | Source |
|-------|--------|
| Trio equal | `VERSION` · `app/version.py` · `version_manifest.json` |
| Changelog row | `docs/CHANGELOG.md` table row for current version |
| Continuity head | `docs/CONTINUITY.md` **Head:** matches |
| Features version | `docs/FEATURES.md` `**Version:**` line (if present) |

Full maintenance cadence: [MAINTENANCE.md](MAINTENANCE.md).
