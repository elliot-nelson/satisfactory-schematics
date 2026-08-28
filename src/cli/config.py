"""Load and validate the root ``config.yaml``.

A typo or unknown top-level key fails loudly (``extra='forbid'``) so misconfiguration is
caught at doctor time rather than deep inside a stage.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = REPO_ROOT / "config.yaml"


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _Lenient(BaseModel):
    """For sub-trees we don't fully model yet (kept permissive on purpose)."""

    model_config = ConfigDict(extra="allow")


class GameConfig(_Model):
    version: str
    engineVersion: str
    appId: int
    path: str | None = None
    requires: list[str] = []


class BlenderTool(_Model):
    version: str
    env: str = "BLENDER"


class DockerTool(_Model):
    minVersion: str | None = None


class BrewTool(_Model):
    brew: str | None = None
    bin: str | None = None


class DotnetTool(_Model):
    optional: bool = True


class ToolsConfig(_Model):
    docker: DockerTool = DockerTool()
    blender: BlenderTool
    potrace: BrewTool = BrewTool()
    rsvg: BrewTool = BrewTool()
    dotnet: DotnetTool = DotnetTool()


class OodleConfig(_Lenient):
    url: str
    entry: str | None = None


class ExtractorConfig(_Lenient):
    oodle: OodleConfig | None = None
    zlib: OodleConfig | None = None


class RenderConfig(_Model):
    ppm: float = 20
    grid: float = 1.0
    metersPerUnit: float = 1.0
    views: list[str] = ["top", "front", "back", "left", "right"]
    defaultTheme: str = "blue-schematic"


class Config(_Model):
    game: GameConfig
    extractor: ExtractorConfig
    tools: ToolsConfig
    render: RenderConfig = RenderConfig()
    buildings: str = "config/buildings.yaml"
    segments: str = "config/segments.yaml"


class ConfigError(Exception):
    """Raised when config.yaml is missing or invalid."""


def load_config(path: Path | None = None) -> Config:
    """Read + validate ``config.yaml``. Raises :class:`ConfigError` with a clear message."""
    cfg_path = path or CONFIG_PATH
    if not cfg_path.exists():
        raise ConfigError(f"config.yaml not found at {cfg_path}")
    try:
        raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"config.yaml is not valid YAML: {exc}") from exc
    try:
        return Config.model_validate(raw)
    except ValidationError as exc:
        raise ConfigError(f"config.yaml failed validation:\n{exc}") from exc
