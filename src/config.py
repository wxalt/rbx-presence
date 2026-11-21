from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

APP_DIRECTORY = Path(os.getenv("APPDATA", Path.home())) / "RBXPresence"
CONFIG_FILE = APP_DIRECTORY / "config.json"

DEFAULT_CONFIG: dict[str, Any] = {
    "client_id": "",
    "asset_key": "rbx_presence",
    "auto_monitor": False,  # démarre la surveillance dès l'ouverture de l'app
}


def load_config() -> dict[str, Any]:
    try:
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            data = {}
    except (OSError, ValueError):
        data = {}

    return {
        "client_id": str(data.get("client_id", DEFAULT_CONFIG["client_id"])).strip(),
        "asset_key": str(data.get("asset_key", DEFAULT_CONFIG["asset_key"])).strip()
        or DEFAULT_CONFIG["asset_key"],
        "auto_monitor": bool(data.get("auto_monitor", DEFAULT_CONFIG["auto_monitor"])),
    }


def save_config(config: dict[str, Any]) -> None:
    """Écriture atomique : pas de config.json corrompu si l'app est tuée."""
    APP_DIRECTORY.mkdir(parents=True, exist_ok=True)
    tmp = CONFIG_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, CONFIG_FILE)
