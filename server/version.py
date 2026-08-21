from __future__ import annotations

import json
from pathlib import Path


def _load_version() -> str:
    root = Path(__file__).resolve().parents[1]
    data = json.loads((root / "VERSION.json").read_text(encoding="utf-8"))
    return str(data["version"])


APP_VERSION = _load_version()
