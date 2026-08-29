"""Filesystem context: where ``build/`` and ``dist/`` live and their step subfolders."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BUILD_DIR = REPO_ROOT / "build"
DIST_DIR = REPO_ROOT / "dist"

# Step-structured build subfolders (see NEW_REPO_PLAN.md 4).
DOCTOR_DIR = BUILD_DIR / "00-doctor"
EXTRACT_DIR = BUILD_DIR / "01-extract"
PREPARE_DIR = BUILD_DIR / "02-prepare"
RENDER_DIR = BUILD_DIR / "03-render"
SVG_DIR = BUILD_DIR / "04-svg"  # per-theme: 04-svg/<theme>/<name>_<view>.svg
PNG_DIR = BUILD_DIR / "05-png"  # per-theme (optional --png): 05-png/<theme>/<name>_<view>.png
PREVIEW_DIR = BUILD_DIR / "06-preview"  # per-theme: 06-preview/<theme>/preview.{html,json}


def ensure(path: Path) -> Path:
    """Create ``path`` (as a directory) if needed and return it."""
    path.mkdir(parents=True, exist_ok=True)
    return path
