"""Render themes: the per-look color + toggle config the finalize stage consumes.

A theme (``themes/<slug>.yaml`` in the repo root) owns the SVG's appearance -- line/fill colors,
port-marker colors, clearance-tick color, and whether those overlay layers draw at all. Everything
upstream of finalize is theme-independent, so a theme is cheap: swap the file, re-run finalize.

``--theme`` accepts either a **path** (relative or absolute, ``~`` expanded -- e.g.
``~/my_themes/xyz.yaml``) or a **bare name** (``xyz``) that resolves to ``themes/xyz.yaml``.
``load_theme(ref)`` resolves + validates the file (unknown keys fail loudly) and exposes ``style()``
-- the flat dict of look knobs the assembler (``src/finalize/svg.py``) and overlays
(``src/annotate/*``) expect. Faithful to the historical defaults from the old ``load_theme.py``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

REPO_ROOT = Path(__file__).resolve().parents[2]
THEMES_DIR = REPO_ROOT / "themes"

# Line-art detail knobs are not part of a theme's *look* (they'd change geometry, not color), so
# they stay fixed at the proven render.py defaults rather than becoming per-theme.
RDP_TOLERANCE = 0.4
FILL_ERODE_PX = 1
STITCH_STROKES = True


class ThemeError(Exception):
    """Raised when a theme file is missing or invalid."""


def _hex_rgb(value: str) -> tuple[int, int, int]:
    """Parse ``#rrggbb`` / ``#rgb`` -> (r, g, b) ints 0..255."""
    h = value.strip().lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) != 6:
        raise ValueError(f"invalid hex color {value!r} (want #rrggbb)")
    return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


class Theme(BaseModel):
    """The validated ``theme:`` block of a theme file. ``slug`` is set post-load from the file stem
    (it names the per-theme output dirs) and is not read from the YAML."""

    model_config = ConfigDict(extra="forbid")

    slug: str = "theme"
    name: str = "theme"
    lineColor: str
    fillColor: str
    fillAlpha: float = 0.30
    lineWidth: float = 1.5
    jitter: float = 0.25
    highlightPorts: bool = True
    inputPortColor: str
    outputPortColor: str
    powerPortColor: str = "#fa9549"  # FICSIT orange power-connector glyph
    showCollisionBoxTicks: bool = True
    collisionBoxColor: str
    collisionBoxAlpha: int = 180

    @field_validator("lineColor", "fillColor", "inputPortColor", "outputPortColor",
                     "powerPortColor", "collisionBoxColor")  # fmt: skip
    @classmethod
    def _valid_hex(cls, v: str) -> str:
        _hex_rgb(v)  # raises on bad input
        return v

    def style(self, potrace: str = "potrace") -> dict[str, Any]:
        """Flatten into the look dict the assembler + overlays consume (see svg.assemble)."""
        line = _hex_rgb(self.lineColor)
        fill = _hex_rgb(self.fillColor)
        return {
            "line_hex": f"#{line[0]:02x}{line[1]:02x}{line[2]:02x}",
            "fill_hex": f"#{fill[0]:02x}{fill[1]:02x}{fill[2]:02x}",
            "fill_alpha": self.fillAlpha,
            "line_width": self.lineWidth,
            "jitter": self.jitter,
            "rdp": RDP_TOLERANCE,
            "stitch": STITCH_STROKES,
            "fill_erode": FILL_ERODE_PX,
            "highlight_ports": self.highlightPorts,
            "show_ticks": self.showCollisionBoxTicks,
            "in_rgb": _hex_rgb(self.inputPortColor),
            "out_rgb": _hex_rgb(self.outputPortColor),
            "power_rgb": _hex_rgb(self.powerPortColor),
            "tick_rgba": (*_hex_rgb(self.collisionBoxColor), self.collisionBoxAlpha),
            "potrace": potrace,
        }


def resolve_theme(ref: str) -> Path:
    """Resolve a ``--theme`` value to a theme file.

    Accepts a **path** (relative or absolute, ``~`` expanded) if it points at an existing file;
    otherwise treats ``ref`` as a **bare name** and looks for ``themes/<ref>.yaml``. Raises
    :class:`ThemeError` (listing what's available) if neither resolves.
    """
    as_path = Path(ref).expanduser()
    if as_path.is_file():
        return as_path
    name = ref if ref.endswith(".yaml") else f"{ref}.yaml"
    candidate = THEMES_DIR / name
    if candidate.is_file():
        return candidate
    available = sorted(p.stem for p in THEMES_DIR.glob("*.yaml")) if THEMES_DIR.is_dir() else []
    hint = f" Available in themes/: {', '.join(available)}." if available else ""
    raise ThemeError(f"theme '{ref}' not found -- not a file, and no themes/{name}.{hint}")


def load_theme(ref: str) -> Theme:
    """Resolve (path or bare name) + validate a theme. Raises :class:`ThemeError` on any problem.

    The returned theme's ``slug`` is the file stem, which names the per-theme output dirs."""
    path = resolve_theme(ref)
    try:
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ThemeError(f"{path.name} could not be read: {exc}") from exc
    if not isinstance(doc, dict) or not isinstance(doc.get("theme"), dict):
        raise ThemeError(f"{path.name}: expected a top-level `theme:` mapping.")
    try:
        theme = Theme.model_validate(doc["theme"])
    except ValidationError as exc:
        raise ThemeError(f"{path.name} failed validation:\n{exc}") from exc
    theme.slug = path.stem
    return theme
