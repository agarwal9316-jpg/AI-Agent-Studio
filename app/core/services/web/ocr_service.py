"""Screen / image OCR — extract text from screenshots (native Windows or tesseract)."""

from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

OCR_RE = re.compile(
    r"<<<OCR>>>\s*(.*?)\s*<<<END_OCR>>>",
    re.DOTALL | re.IGNORECASE,
)


def tool_instructions() -> str:
    return """
## OCR (read text from image / screenshot)

<<<OCR>>>
path: C:\\path\\to\\image.png
<<<END_OCR>>>

Or empty path to OCR the latest screenshot in data/screenshots if present.
Uses Windows OCR when available, else Tesseract if installed.
""".strip()


def extract_ocr_blocks(text: str) -> list[str]:
    out = []
    for m in OCR_RE.finditer(text or ""):
        body = (m.group(1) or "").strip()
        path = ""
        for line in body.splitlines():
            if line.lower().startswith("path:"):
                path = line.split(":", 1)[1].strip()
            elif not path and line.strip():
                path = line.strip()
        out.append(path)
    return out


def _ocr_tesseract(path: Path) -> str | None:
    try:
        import pytesseract  # type: ignore
        from PIL import Image  # type: ignore

        return pytesseract.image_to_string(Image.open(path))
    except Exception:  # noqa: BLE001
        return None


def _ocr_windows(path: Path) -> str | None:
    """Windows.Media.Ocr via PowerShell (Windows 10+)."""
    try:
        # Use WinRT through PowerShell is heavy; try simple approach with Windows.Media.Ocr
        ps = rf"""
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Storage.StorageFile,Windows.Storage,ContentType=WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder,Windows.Graphics,ContentType=WindowsRuntime]
$null = [Windows.Media.Ocr.OcrEngine,Windows.Foundation,ContentType=WindowsRuntime]
function Await($WinRtTask, $ResultType) {{
  $asTask = [System.WindowsRuntimeSystemExtensions]::AsTask($WinRtTask, [System.Threading.CancellationToken]::None)
  $asTask.Wait(-1) | Out-Null
  return $asTask.Result
}}
$path = '{str(path).replace("'", "''")}'
$file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($path)) ([Windows.Storage.StorageFile])
$stream = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
$decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
$bitmap = Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
$engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
if ($null -eq $engine) {{ Write-Output ''; exit 0 }}
$result = Await ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
Write-Output $result.Text
"""
        with tempfile.NamedTemporaryFile("w", suffix=".ps1", delete=False, encoding="utf-8") as f:
            f.write(ps)
            script = f.name
        try:
            proc = subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", script],
                capture_output=True,
                text=True,
                timeout=60,
            )
            out = (proc.stdout or "").strip()
            return out or None
        finally:
            Path(script).unlink(missing_ok=True)
    except Exception:  # noqa: BLE001
        return None


def ocr_image(path: str | Path) -> dict[str, Any]:
    p = Path(path).expanduser()
    if not p.is_file():
        # latest screenshot fallback
        from app.paths import data_dir

        shots = sorted((data_dir() / "screenshots").glob("*.png"), key=lambda x: x.stat().st_mtime, reverse=True)
        if not path and shots:
            p = shots[0]
        elif shots and not p.is_file():
            p = shots[0]
        else:
            return {"ok": False, "error": f"Image not found: {path}"}
    text = _ocr_tesseract(p)
    engine = "tesseract"
    if text is None:
        text = _ocr_windows(p)
        engine = "windows_ocr"
    if text is None:
        return {
            "ok": False,
            "error": (
                "OCR unavailable. Install Tesseract (and pytesseract) "
                "or use Windows 10+ OCR languages pack."
            ),
            "path": str(p),
        }
    return {"ok": True, "path": str(p.resolve()), "engine": engine, "text": text.strip()}
