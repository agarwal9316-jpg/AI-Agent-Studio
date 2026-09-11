"""Backward-compatible entry → ensure_native (Launch.bat uses that). """

from app.tools.ensure_native import main

if __name__ == "__main__":
    raise SystemExit(main())
