#!/usr/bin/env python3
"""Materialize control plane backend + Control plane UI page."""
from __future__ import annotations
import base64
import zlib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAYLOAD = ROOT / "scripts" / "refactor_payload"
PARTS = ROOT / "scripts" / "cp_parts"
EMBED_PARTS = ROOT / "scripts" / "cp_embed_parts"
PREFIX = "cp_ui"


def _run_embedded() -> bool:
    chunks = sorted(EMBED_PARTS.glob("embed.p*.txt"))
    if not chunks:
        emb = ROOT / "scripts" / "install_cp_embedded.py"
        if emb.is_file() and emb.stat().st_size > 5000:
            subprocess.run([sys.executable, str(emb)], cwd=str(ROOT), check=False)
            return True
        return False
    text = "".join(p.read_text(encoding="utf-8") for p in chunks)
    dest = ROOT / "scripts" / "install_cp_embedded.py"
    dest.write_text(text, encoding="utf-8")
    subprocess.run([sys.executable, str(dest)], cwd=str(ROOT), check=False)
    return True


def _join_parts() -> bool:
    targets = {
        "store": ROOT / "app/core/services/control_plane/store.py",
        "service": ROOT / "app/core/services/control_plane/service.py",
        "page": ROOT / "app/ui/pages/control_plane_page.py",
    }
    any_done = False
    for key, dest in targets.items():
        chunks = sorted(PARTS.glob(f"{key}.p*.txt"))
        if not chunks:
            continue
        text = "".join(p.read_text(encoding="utf-8") for p in chunks)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text, encoding="utf-8")
        print("wrote", dest, len(text), "chars")
        any_done = True
    return any_done


def _load_b64() -> str:
    texts = []
    for i in range(20):
        p = PAYLOAD / f"{PREFIX}.z{i:02d}.b64"
        a = PAYLOAD / f"{PREFIX}.z{i:02d}a.b64"
        b = PAYLOAD / f"{PREFIX}.z{i:02d}b.b64"
        if a.exists():
            t = a.read_text(encoding="utf-8").strip()
            if b.exists():
                t += b.read_text(encoding="utf-8").strip()
            if t and not t.startswith("PLACEHOLDER") and len(t) > 50:
                texts.append(t)
        elif p.exists():
            t = p.read_text(encoding="utf-8").strip()
            if t.startswith("PLACEHOLDER") or len(t) < 100:
                continue
            texts.append(t)
    return "".join(texts)


def _from_payload() -> bool:
    b64 = _load_b64()
    if not b64:
        return False
    pad = "=" * (-len(b64) % 4)
    try:
        raw = zlib.decompress(base64.b64decode(b64 + pad))
    except Exception as e:
        print("payload decompress failed:", e)
        return False
    if b"\n--\n" not in raw:
        print("payload missing header separator")
        return False
    header, body = raw.split(b"\n--\n", 1)
    offset = 0
    for line in header.decode().splitlines():
        if "|" not in line:
            continue
        path_s, size_s = line.split("|", 1)
        size = int(size_s)
        data = body[offset : offset + size]
        offset += size
        dest = ROOT / path_s
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        print("wrote", dest, len(data), "bytes")
    return True


def main() -> None:
    if _run_embedded():
        print("Control plane UI + modules installed (embedded).")
        return
    ok = _join_parts()
    if not ok:
        ok = _from_payload()
    if not ok:
        print("No control plane parts or payload found")
        return
    print("Control plane UI + modules installed.")


if __name__ == "__main__":
    main()
