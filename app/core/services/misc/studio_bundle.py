"""Export / import a portable studio data bundle (zip).

Roadmap: full studio bundle under ``data/`` — settings/config (secrets redacted
by default), knowledge, notes, channels, automations, chats metadata, artifacts
index. Soft-degrades on bad zips; never raises to crash the app.
"""

from __future__ import annotations

import json
import re
import shutil
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.paths import data_dir

BUNDLE_FORMAT = 1
MANIFEST_NAME = "studio_bundle.json"
ZIP_DATA_PREFIX = "data/"

# Secret-ish JSON keys (case-insensitive match on leaf keys).
_SECRET_KEY_RE = re.compile(
    r"(?i)^(api_?key|.*_api_key|llm_api_key|fallback_api_key|password|secret|"
    r"token|auth_token|access_token|refresh_token|authorization|"
    r"eleven.?labs.?key|voice_eleven.*key|private_key)$"
)

# Relative paths (under data/) always considered for export when present.
_FILE_TARGETS: tuple[str, ...] = (
    "config.json",
    "providers.json",
    "automations.json",
    "chats/index.json",
    "artifacts/index.json",
)

_DIR_TARGETS: tuple[str, ...] = (
    "notes",
    "channels",
    "knowledge",
)

# Within artifacts/, only index.json (not blobs/).
_ARTIFACTS_INDEX_ONLY = True


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _resolve_data_root(data_root: Path | str | None) -> Path:
    if data_root is None:
        return data_dir()
    return Path(data_root)


def _is_secret_key(key: str) -> bool:
    return bool(_SECRET_KEY_RE.match(str(key or "").strip()))


def redact_secrets(obj: Any) -> Any:
    """Deep-copy-ish redact of secret fields in JSON-compatible structures."""
    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        for k, v in obj.items():
            ks = str(k)
            if _is_secret_key(ks):
                # Preserve shape: empty string for strings, empty list/dict kept empty
                if isinstance(v, str):
                    out[ks] = "" if not v else "***REDACTED***"
                elif isinstance(v, list):
                    out[ks] = []
                elif isinstance(v, dict):
                    out[ks] = {}
                elif v is None:
                    out[ks] = None
                else:
                    out[ks] = "***REDACTED***"
            elif ks == "keys" and isinstance(v, list):
                # providers.json: keys = [{id, label, key, ...}]
                redacted_keys = []
                for item in v:
                    if isinstance(item, dict):
                        item2 = dict(item)
                        if "key" in item2 and item2.get("key"):
                            item2["key"] = "***REDACTED***"
                        redacted_keys.append(item2)
                    else:
                        redacted_keys.append(item)
                out[ks] = redacted_keys
            else:
                out[ks] = redact_secrets(v)
        return out
    if isinstance(obj, list):
        return [redact_secrets(x) for x in obj]
    return obj


def _read_json_file(path: Path) -> Any | None:
    try:
        if not path.is_file():
            return None
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def _write_json_file(path: Path, payload: Any) -> bool:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(path)
        return True
    except Exception:  # noqa: BLE001
        return False


def list_bundle_sections() -> list[dict[str, str]]:
    """Human-readable inventory of what the bundle includes / excludes."""
    return [
        {
            "id": "config",
            "include": "data/config.json (API keys redacted by default)",
            "exclude": "",
        },
        {
            "id": "providers",
            "include": "data/providers.json (key material redacted by default)",
            "exclude": "",
        },
        {
            "id": "automations",
            "include": "data/automations.json",
            "exclude": "",
        },
        {
            "id": "chats_meta",
            "include": "data/chats/index.json (titles/pins/folders only)",
            "exclude": "Full chat message bodies (chats/<id>.json)",
        },
        {
            "id": "notes",
            "include": "data/notes/*.json",
            "exclude": "",
        },
        {
            "id": "channels",
            "include": "data/channels/ (index + channel timelines)",
            "exclude": "",
        },
        {
            "id": "knowledge",
            "include": "data/knowledge/ (rag.sqlite + sources)",
            "exclude": "",
        },
        {
            "id": "artifacts_index",
            "include": "data/artifacts/index.json",
            "exclude": "Artifact blobs under data/artifacts/blobs/",
        },
        {
            "id": "secrets",
            "include": "Optional with include_secrets=True",
            "exclude": "Raw API keys / tokens by default",
        },
        {
            "id": "other",
            "include": "",
            "exclude": "runs, logs, generated_images, browser_shots, team_channels, company, agents, …",
        },
    ]


def _iter_export_paths(root: Path) -> list[tuple[str, Path]]:
    """Return list of (arcname relative with data/ prefix, absolute path)."""
    out: list[tuple[str, Path]] = []
    seen: set[str] = set()

    def add(rel: str, abs_path: Path) -> None:
        rel = rel.replace("\\", "/").lstrip("/")
        if rel in seen:
            return
        if not abs_path.exists():
            return
        seen.add(rel)
        out.append((f"{ZIP_DATA_PREFIX}{rel}", abs_path))

    for rel in _FILE_TARGETS:
        add(rel, root / rel)

    for drel in _DIR_TARGETS:
        dpath = root / drel
        if not dpath.is_dir():
            continue
        for p in dpath.rglob("*"):
            if not p.is_file():
                continue
            # skip temp / cache junk
            if p.name.endswith(".tmp") or p.name.endswith(".pyc"):
                continue
            if "__pycache__" in p.parts:
                continue
            try:
                rel = p.relative_to(root).as_posix()
            except ValueError:
                continue
            add(rel, p)

    return out


def _prepare_json_bytes(path: Path, *, include_secrets: bool, rel: str) -> bytes | None:
    """Load JSON and optionally redact; return UTF-8 bytes. None → copy raw file."""
    # Only redact known secret-bearing JSON configs
    name = Path(rel).name
    if name not in ("config.json", "providers.json") and "config" not in name:
        # Still redact any json that looks like it has api keys if not include_secrets
        if include_secrets or path.suffix.lower() != ".json":
            return None
        # For other JSON (notes, channels, automations, indexes) — light redact
        data = _read_json_file(path)
        if data is None:
            return None
        try:
            red = redact_secrets(data) if not include_secrets else data
            return (json.dumps(red, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
        except Exception:  # noqa: BLE001
            return None

    data = _read_json_file(path)
    if data is None:
        return None
    try:
        payload = data if include_secrets else redact_secrets(data)
        return (json.dumps(payload, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    except Exception:  # noqa: BLE001
        return None


def export_studio_bundle(
    dest_zip: Path | str,
    *,
    include_secrets: bool = False,
    data_root: Path | str | None = None,
) -> dict[str, Any]:
    """Write a portable ``.zip`` of selected studio data.

    Returns ``{ok, path, files, include_secrets, error?}`` — never raises.
    """
    try:
        root = _resolve_data_root(data_root)
        dest = Path(dest_zip)
        dest.parent.mkdir(parents=True, exist_ok=True)

        entries = _iter_export_paths(root)
        files_meta: list[dict[str, Any]] = []

        # Write to a temp zip then replace dest (atomic-ish)
        tmp_fd_dir = tempfile.mkdtemp(prefix="studio_bundle_export_")
        tmp_zip = Path(tmp_fd_dir) / "bundle.zip"
        try:
            with zipfile.ZipFile(tmp_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                manifest = {
                    "format": BUNDLE_FORMAT,
                    "created_at": _now(),
                    "include_secrets": bool(include_secrets),
                    "app": "AI Agent Studio",
                    "sections": [s["id"] for s in list_bundle_sections()],
                    "files": [],
                }
                for arc, abs_path in entries:
                    rel = arc[len(ZIP_DATA_PREFIX) :] if arc.startswith(ZIP_DATA_PREFIX) else arc
                    try:
                        if abs_path.suffix.lower() == ".json":
                            raw = _prepare_json_bytes(
                                abs_path, include_secrets=include_secrets, rel=rel
                            )
                            if raw is not None:
                                zf.writestr(arc, raw)
                                files_meta.append(
                                    {
                                        "path": rel,
                                        "bytes": len(raw),
                                        "redacted": not include_secrets
                                        and Path(rel).name
                                        in ("config.json", "providers.json"),
                                    }
                                )
                                continue
                        # binary / fallback
                        zf.write(abs_path, arcname=arc)
                        files_meta.append(
                            {
                                "path": rel,
                                "bytes": int(abs_path.stat().st_size),
                                "redacted": False,
                            }
                        )
                    except Exception as e:  # noqa: BLE001
                        files_meta.append({"path": rel, "error": str(e)})

                manifest["files"] = [
                    {"path": f.get("path"), "bytes": f.get("bytes", 0)}
                    for f in files_meta
                    if "error" not in f
                ]
                manifest["file_count"] = len(manifest["files"])
                zf.writestr(
                    MANIFEST_NAME,
                    json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
                )

            # Move into place
            if dest.exists():
                dest.unlink()
            shutil.move(str(tmp_zip), str(dest))
        finally:
            shutil.rmtree(tmp_fd_dir, ignore_errors=True)

        return {
            "ok": True,
            "path": str(dest),
            "files": files_meta,
            "file_count": sum(1 for f in files_meta if "error" not in f),
            "include_secrets": bool(include_secrets),
            "created_at": _now(),
        }
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e), "path": str(dest_zip), "files": []}


def _safe_member_path(name: str) -> str | None:
    """Normalize zip member to a data/-relative path, or None if unsafe / skip."""
    name = name.replace("\\", "/").lstrip("/")
    if not name or name.endswith("/"):
        return None
    if name == MANIFEST_NAME:
        return None  # handled separately
    if name.startswith(ZIP_DATA_PREFIX):
        rel = name[len(ZIP_DATA_PREFIX) :]
    elif name.startswith("data"):
        # tolerate missing slash
        rel = name[4:].lstrip("/")
    else:
        # allow bare relative paths that look like our targets
        rel = name
    if not rel or rel.startswith("/") or ".." in Path(rel).parts:
        return None
    return rel


def _is_allowed_import_rel(rel: str) -> bool:
    rel = rel.replace("\\", "/")
    if rel in _FILE_TARGETS:
        return True
    for d in _DIR_TARGETS:
        if rel == d or rel.startswith(d + "/"):
            return True
    # artifacts index only
    if rel == "artifacts/index.json":
        return True
    return False


def _clear_category(root: Path, category: str) -> None:
    """Best-effort clear of a category for replace mode."""
    try:
        if category == "notes":
            d = root / "notes"
            if d.is_dir():
                for p in d.glob("*.json"):
                    try:
                        p.unlink()
                    except OSError:
                        pass
        elif category == "channels":
            d = root / "channels"
            if d.is_dir():
                for p in d.rglob("*"):
                    if p.is_file():
                        try:
                            p.unlink()
                        except OSError:
                            pass
        elif category == "knowledge":
            d = root / "knowledge"
            if d.is_dir():
                shutil.rmtree(d, ignore_errors=True)
        elif category == "automations":
            p = root / "automations.json"
            if p.is_file():
                try:
                    p.unlink()
                except OSError:
                    pass
        elif category == "chats_meta":
            p = root / "chats" / "index.json"
            if p.is_file():
                try:
                    p.unlink()
                except OSError:
                    pass
        elif category == "artifacts_index":
            p = root / "artifacts" / "index.json"
            if p.is_file():
                try:
                    p.unlink()
                except OSError:
                    pass
        elif category == "config":
            # replace will overwrite; no delete needed
            pass
        elif category == "providers":
            pass
    except Exception:  # noqa: BLE001
        pass


def _merge_json_index(existing: Any, incoming: Any, *, id_key: str = "id") -> Any:
    """Merge list-bearing index-like dicts by id; incoming wins on conflict."""
    if not isinstance(incoming, dict):
        return existing if existing is not None else incoming
    if not isinstance(existing, dict):
        return incoming
    out = dict(existing)
    for k, v in incoming.items():
        if k in ("chats", "folders", "items", "channels", "automations") and isinstance(
            v, list
        ):
            prev = out.get(k) if isinstance(out.get(k), list) else []
            by_id: dict[str, Any] = {}
            order: list[str] = []
            for item in prev:
                if isinstance(item, dict) and item.get(id_key):
                    iid = str(item[id_key])
                    by_id[iid] = item
                    order.append(iid)
            for item in v:
                if isinstance(item, dict) and item.get(id_key):
                    iid = str(item[id_key])
                    if iid not in by_id:
                        order.append(iid)
                    by_id[iid] = item
                else:
                    # append non-id items
                    prev_list = out.get(k) if isinstance(out.get(k), list) else []
                    # handled below via rebuilt list — keep as synthetic
                    by_id[f"__anon_{len(by_id)}"] = item
                    order.append(f"__anon_{len(by_id)-1}")
            out[k] = [by_id[i] for i in order if i in by_id]
        elif k == "active_id" and v:
            out[k] = v
        else:
            # scalar / other: incoming wins
            out[k] = v
    return out


def import_studio_bundle(
    src_zip: Path | str,
    *,
    mode: str = "merge",
    data_root: Path | str | None = None,
) -> dict[str, Any]:
    """Restore from a studio bundle zip.

    ``mode``: ``merge`` (default) or ``replace`` for included categories.

    Returns ``{ok, mode, restored, skipped, warnings, error?}`` — never raises.
    """
    restored: list[str] = []
    skipped: list[str] = []
    warnings: list[str] = []
    try:
        src = Path(src_zip)
        if not src.is_file():
            return {
                "ok": False,
                "error": f"Bundle not found: {src}",
                "restored": [],
                "skipped": [],
                "warnings": [],
            }
        mode_n = (mode or "merge").strip().lower()
        if mode_n not in ("merge", "replace"):
            mode_n = "merge"

        root = _resolve_data_root(data_root)
        root.mkdir(parents=True, exist_ok=True)

        try:
            zf = zipfile.ZipFile(src, "r")
        except zipfile.BadZipFile as e:
            return {
                "ok": False,
                "error": f"Not a valid zip: {e}",
                "restored": [],
                "skipped": [],
                "warnings": ["bad_zip"],
            }
        except Exception as e:  # noqa: BLE001
            return {
                "ok": False,
                "error": f"Cannot open zip: {e}",
                "restored": [],
                "skipped": [],
                "warnings": [],
            }

        with zf:
            names = zf.namelist()
            # Soft-check manifest
            manifest: dict[str, Any] = {}
            if MANIFEST_NAME in names:
                try:
                    manifest = json.loads(zf.read(MANIFEST_NAME).decode("utf-8"))
                    if int(manifest.get("format") or 0) not in (0, BUNDLE_FORMAT, 1):
                        warnings.append(
                            f"Unknown bundle format {manifest.get('format')}; trying anyway"
                        )
                except Exception:  # noqa: BLE001
                    warnings.append("manifest_unreadable")
            else:
                warnings.append("missing_manifest")

            # Collect allowed members
            members: list[tuple[str, str]] = []  # (zip_name, rel)
            for name in names:
                rel = _safe_member_path(name)
                if rel is None:
                    if name not in (MANIFEST_NAME,) and not name.endswith("/"):
                        skipped.append(name)
                    continue
                if not _is_allowed_import_rel(rel):
                    skipped.append(rel)
                    continue
                # never import artifact blobs even if present in older zips
                if rel.startswith("artifacts/blobs/") or "/blobs/" in rel:
                    skipped.append(rel)
                    continue
                members.append((name, rel))

            if not members:
                return {
                    "ok": False,
                    "error": "Zip has no recognized studio data files",
                    "restored": [],
                    "skipped": skipped,
                    "warnings": warnings,
                    "manifest": manifest,
                }

            if mode_n == "replace":
                # Clear categories that appear in the zip
                cats: set[str] = set()
                for _, rel in members:
                    if rel in ("config.json",):
                        cats.add("config")
                    elif rel in ("providers.json",):
                        cats.add("providers")
                    elif rel == "automations.json":
                        cats.add("automations")
                    elif rel == "chats/index.json":
                        cats.add("chats_meta")
                    elif rel == "artifacts/index.json":
                        cats.add("artifacts_index")
                    elif rel.startswith("notes/"):
                        cats.add("notes")
                    elif rel.startswith("channels/"):
                        cats.add("channels")
                    elif rel.startswith("knowledge/"):
                        cats.add("knowledge")
                for c in cats:
                    _clear_category(root, c)

            for zip_name, rel in members:
                dest = root / rel
                try:
                    data = zf.read(zip_name)
                except Exception as e:  # noqa: BLE001
                    warnings.append(f"read_fail:{rel}:{e}")
                    continue

                # Merge JSON indexes / config when mode=merge
                if (
                    mode_n == "merge"
                    and rel.endswith(".json")
                    and rel
                    in (
                        "config.json",
                        "providers.json",
                        "automations.json",
                        "chats/index.json",
                        "artifacts/index.json",
                        "channels/index.json",
                    )
                ):
                    try:
                        incoming = json.loads(data.decode("utf-8"))
                    except Exception:  # noqa: BLE001
                        incoming = None
                    existing = _read_json_file(dest)
                    if incoming is not None:
                        if rel == "config.json" and isinstance(incoming, dict):
                            base = existing if isinstance(existing, dict) else {}
                            merged = dict(base)
                            merged.update(incoming)
                            # Don't clobber existing secrets with redacted placeholders
                            for k, v in list(merged.items()):
                                if _is_secret_key(str(k)) and (
                                    v in ("", "***REDACTED***")
                                    and isinstance(base.get(k), str)
                                    and base.get(k)
                                    and base.get(k) not in ("", "***REDACTED***")
                                ):
                                    merged[k] = base[k]
                            if not _write_json_file(dest, merged):
                                warnings.append(f"write_fail:{rel}")
                            else:
                                restored.append(rel)
                            continue
                        if rel == "providers.json" and isinstance(incoming, dict):
                            merged_p = _merge_providers(existing, incoming)
                            if not _write_json_file(dest, merged_p):
                                warnings.append(f"write_fail:{rel}")
                            else:
                                restored.append(rel)
                            continue
                        if rel == "automations.json":
                            merged_a = _merge_automations(existing, incoming)
                            if not _write_json_file(dest, merged_a):
                                warnings.append(f"write_fail:{rel}")
                            else:
                                restored.append(rel)
                            continue
                        if rel in (
                            "chats/index.json",
                            "artifacts/index.json",
                            "channels/index.json",
                        ):
                            id_key = "id"
                            merged_i = _merge_json_index(existing, incoming, id_key=id_key)
                            if not _write_json_file(dest, merged_i):
                                warnings.append(f"write_fail:{rel}")
                            else:
                                restored.append(rel)
                            continue

                # Default: write bytes (notes, channel files, knowledge db, replace mode)
                try:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(data)
                    restored.append(rel)
                except Exception as e:  # noqa: BLE001
                    warnings.append(f"write_fail:{rel}:{e}")

        return {
            "ok": True,
            "mode": mode_n,
            "restored": restored,
            "skipped": skipped,
            "warnings": warnings,
            "restored_count": len(restored),
            "manifest": manifest,
        }
    except Exception as e:  # noqa: BLE001
        return {
            "ok": False,
            "error": str(e),
            "restored": restored,
            "skipped": skipped,
            "warnings": warnings,
        }


def _merge_providers(existing: Any, incoming: Any) -> Any:
    if not isinstance(incoming, dict):
        return existing if existing is not None else incoming
    if not isinstance(existing, dict):
        return incoming
    out = dict(existing)
    # top-level scalars from incoming
    for k in ("active_provider_id", "active_key_id", "active_model", "updated_at"):
        if incoming.get(k) not in (None, ""):
            out[k] = incoming[k]
    inc_provs = incoming.get("providers") if isinstance(incoming.get("providers"), list) else []
    ex_provs = out.get("providers") if isinstance(out.get("providers"), list) else []
    by_id: dict[str, Any] = {}
    order: list[str] = []
    for p in ex_provs:
        if isinstance(p, dict) and p.get("id"):
            pid = str(p["id"])
            by_id[pid] = p
            order.append(pid)
    for p in inc_provs:
        if not isinstance(p, dict) or not p.get("id"):
            continue
        pid = str(p["id"])
        if pid not in by_id:
            order.append(pid)
            by_id[pid] = p
            continue
        # merge provider; preserve non-redacted keys
        old = by_id[pid]
        merged = dict(old)
        for pk, pv in p.items():
            if pk == "keys" and isinstance(pv, list):
                old_keys = {
                    str(k.get("id") or ""): k
                    for k in (old.get("keys") or [])
                    if isinstance(k, dict)
                }
                new_keys = []
                seen_kids: set[str] = set()
                for nk in pv:
                    if not isinstance(nk, dict):
                        continue
                    kid = str(nk.get("id") or "")
                    key_val = nk.get("key")
                    if key_val in ("", "***REDACTED***") and kid in old_keys:
                        # keep existing secret
                        new_keys.append(old_keys[kid])
                    else:
                        new_keys.append(nk)
                    if kid:
                        seen_kids.add(kid)
                # keep old keys not in incoming
                for kid, ok in old_keys.items():
                    if kid and kid not in seen_kids:
                        new_keys.append(ok)
                merged["keys"] = new_keys
            else:
                merged[pk] = pv
        by_id[pid] = merged
    out["providers"] = [by_id[i] for i in order if i in by_id]
    return out


def _merge_automations(existing: Any, incoming: Any) -> Any:
    """automations.json may be {items:[...]} or a bare list."""
    if isinstance(incoming, list):
        inc_items = incoming
        inc_wrap = False
    elif isinstance(incoming, dict):
        inc_items = incoming.get("items") or incoming.get("automations") or []
        if not isinstance(inc_items, list):
            inc_items = []
        inc_wrap = True
    else:
        return existing if existing is not None else incoming

    if isinstance(existing, list):
        ex_items = existing
        wrap = False
    elif isinstance(existing, dict):
        ex_items = existing.get("items") or existing.get("automations") or []
        if not isinstance(ex_items, list):
            ex_items = []
        wrap = True
    else:
        ex_items = []
        wrap = inc_wrap

    by_id: dict[str, Any] = {}
    order: list[str] = []
    for it in ex_items:
        if isinstance(it, dict) and it.get("id"):
            iid = str(it["id"])
            by_id[iid] = it
            order.append(iid)
    for it in inc_items:
        if isinstance(it, dict) and it.get("id"):
            iid = str(it["id"])
            if iid not in by_id:
                order.append(iid)
            by_id[iid] = it
    merged_list = [by_id[i] for i in order if i in by_id]
    if wrap or inc_wrap:
        base = existing if isinstance(existing, dict) else {}
        out = dict(base) if isinstance(base, dict) else {}
        if isinstance(incoming, dict):
            for k, v in incoming.items():
                if k not in ("items", "automations"):
                    out[k] = v
        out["items"] = merged_list
        return out
    return merged_list


def describe_bundle(src_zip: Path | str) -> dict[str, Any]:
    """Peek at a zip without importing. Soft-degrades."""
    try:
        src = Path(src_zip)
        if not src.is_file():
            return {"ok": False, "error": "not found"}
        with zipfile.ZipFile(src, "r") as zf:
            names = zf.namelist()
            manifest = {}
            if MANIFEST_NAME in names:
                try:
                    manifest = json.loads(zf.read(MANIFEST_NAME).decode("utf-8"))
                except Exception:  # noqa: BLE001
                    manifest = {}
            data_files = []
            for n in names:
                rel = _safe_member_path(n)
                if rel:
                    data_files.append(rel)
            return {
                "ok": True,
                "manifest": manifest,
                "files": data_files,
                "file_count": len(data_files),
            }
    except zipfile.BadZipFile as e:
        return {"ok": False, "error": f"bad zip: {e}"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}
