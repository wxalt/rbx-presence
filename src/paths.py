"""Chemins des ressources, compatibles dev + PyInstaller (onefile/onedir)."""
from __future__ import annotations

import sys
from pathlib import Path

if getattr(sys, "frozen", False):
    BASE_DIR = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
else:
    BASE_DIR = Path(__file__).resolve().parent.parent

ASSETS_DIR = BASE_DIR / "assets"


def asset(name: str) -> Path:
    return ASSETS_DIR / name
