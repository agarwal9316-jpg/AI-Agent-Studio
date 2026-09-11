"""Roadmap — Optional icons / branding pack (1.28.2)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.version import __version__  # noqa: E402
from app.core.services.system import branding  # noqa: E402

BRAND = ROOT / "assets" / "branding"
DOC = ROOT / "docs" / "BRANDING.md"
GEN = ROOT / "scripts" / "generate_branding_assets.py"
SPEC = ROOT / "AI-Agent-Studio.spec"


def test_version():
    assert __version__ == "1.28.2", __version__
    file_ver = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    assert file_ver == "1.28.2", file_ver
    print("✓ version 1.28.2")


def test_assets_exist():
    assert BRAND.is_dir(), f"missing {BRAND}"
    required = [
        "app_icon_256.png",
        "app_icon_64.png",
        "app_icon_32.png",
        "tray_icon.png",
        "logo.svg",
        "app_icon.ico",
    ]
    for name in required:
        p = BRAND / name
        assert p.is_file(), f"missing {p}"
        assert p.stat().st_size > 40, f"too small: {p}"
    print("✓ assets/branding pack files present")


def test_loader_finds_pack():
    assert branding.pack_present() is True
    st = branding.status()
    assert st["present"] is True
    assert st["icons"]["256"] and st["icons"]["64"] and st["icons"]["32"]
    assert st["logo_svg"] is True
    assert st["ico"] is True
    assert st["tray"] is True
    assert branding.best_icon_png(256) is not None
    assert branding.icon_png(64) is not None
    assert branding.ico_path() is not None
    assert branding.logo_svg() is not None
    assert branding.tray_icon_path() is not None
    print("✓ branding loader finds pack")


def test_pil_load_soft():
    img = branding.load_pil_image(32)
    assert img is not None
    assert img.size == (32, 32)
    print("✓ Pillow load resize")


def test_docs_and_generator():
    assert DOC.is_file(), f"missing {DOC}"
    doc = DOC.read_text(encoding="utf-8")
    for needle in (
        "assets/branding",
        "app_icon_256.png",
        "generate_branding_assets",
        "soft-degrade",
        "PyInstaller",
    ):
        assert needle.lower() in doc.lower(), needle
    assert GEN.is_file(), f"missing {GEN}"
    gen = GEN.read_text(encoding="utf-8")
    assert "Pillow" in gen or "PIL" in gen
    assert "app_icon.ico" in gen
    roadmap = (ROOT / "docs" / "ROADMAP.md").read_text(encoding="utf-8")
    assert "Optional icons / branding pack" in roadmap
    assert "- [x] Optional icons / branding pack" in roadmap
    print("✓ docs/BRANDING.md + generator + ROADMAP checkbox")


def test_spec_wires_ico():
    text = SPEC.read_text(encoding="utf-8")
    assert "assets/branding" in text
    assert "app_icon.ico" in text
    assert "icon=" in text
    print("✓ PyInstaller spec bundles branding + icon")


def test_app_window_hooks():
    aw = (ROOT / "app" / "ui" / "app_window.py").read_text(encoding="utf-8")
    assert "apply_window_icon" in aw
    assert "_about_brand_image" in aw or "ctk_brand_image" in aw
    assert "_home_brand_image" in aw or "ctk_brand_image" in aw
    assert "Brand accent" in aw
    print("✓ app_window wires icon / About / Home / Appearance")


def test_soft_degrade_missing(tmp_path):
    """Loader returns falsey when pack dir empty — without raising."""
    import app.core.services.system.branding as b

    empty = tmp_path / "branding"
    empty.mkdir()
    orig = b.branding_dir
    b.branding_dir = lambda: empty  # type: ignore[method-assign]
    try:
        assert b.pack_present() is False
        assert b.best_icon_png() is None
        assert b.apply_window_icon(None) is False
        assert b.ctk_brand_image() is None
    finally:
        b.branding_dir = orig  # type: ignore[method-assign]
    print("✓ soft-degrade when pack missing")


if __name__ == "__main__":
    test_version()
    test_assets_exist()
    test_loader_finds_pack()
    test_pil_load_soft()
    test_docs_and_generator()
    test_spec_wires_ico()
    test_app_window_hooks()
    # soft degrade without pytest fixtures
    import tempfile
    from pathlib import Path as P

    with tempfile.TemporaryDirectory() as td:
        class _T:
            pass
        # inline
        import app.core.services.system.branding as b

        empty = P(td) / "branding"
        empty.mkdir()
        orig = b.branding_dir
        b.branding_dir = lambda: empty  # type: ignore
        try:
            assert b.pack_present() is False
            assert b.apply_window_icon(None) is False
        finally:
            b.branding_dir = orig  # type: ignore
        print("✓ soft-degrade when pack missing")
    print("\nAll branding tests passed.")
