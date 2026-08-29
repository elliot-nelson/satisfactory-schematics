"""Load and validate ``config/config.yaml`` (+ machine-local ``config/config.local.yaml``).

A typo or unknown top-level key fails loudly (``extra='forbid'``) so misconfiguration is
caught at doctor time rather than deep inside a stage.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = REPO_ROOT / "config" / "config.yaml"
# Machine-local overrides + cache. NOT committed (see .gitignore). Merged over config.yaml.
LOCAL_CONFIG_PATH = REPO_ROOT / "config" / "config.local.yaml"

_LOCAL_HEADER = (
    "# config/config.local.yaml -- machine-local overrides + cache (NOT committed).\n"
    "# Deep-merged over config/config.yaml at load time (local values win).\n"
    "# Partly managed by `schematic doctor` (e.g. the detected game path); safe to hand-edit.\n"
)


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
    segmentViews: list[str] = ["top", "front"]
    segmentLengths: list[int] = [1, 2, 4, 8]
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


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge ``override`` onto ``base`` (override wins; nested dicts merged)."""
    result = dict(base)
    for key, value in override.items():
        existing = result.get(key)
        if isinstance(existing, dict) and isinstance(value, dict):
            result[key] = _deep_merge(existing, value)
        else:
            result[key] = value
    return result


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigError(f"{path.name} is not valid YAML: {exc}") from exc
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ConfigError(f"{path.name} must be a YAML mapping at the top level")
    return data


def load_local(local_path: Path | None = None) -> dict[str, Any]:
    """Return the raw (unvalidated) contents of config.local.yaml, or ``{}`` if absent."""
    return _read_yaml(local_path or LOCAL_CONFIG_PATH)


def save_local(data: dict[str, Any], local_path: Path | None = None) -> None:
    """Overwrite config.local.yaml with ``data`` (plus the standard header)."""
    dest = local_path or LOCAL_CONFIG_PATH
    body = yaml.safe_dump(data, sort_keys=False, default_flow_style=False)
    dest.write_text(_LOCAL_HEADER + body, encoding="utf-8")


def update_local(updates: dict[str, Any], local_path: Path | None = None) -> None:
    """Deep-merge ``updates`` into config.local.yaml and write it back."""
    dest = local_path or LOCAL_CONFIG_PATH
    merged = _deep_merge(load_local(dest), updates)
    save_local(merged, dest)


def load_config(path: Path | None = None, local_path: Path | None = None) -> Config:
    """Read config.yaml, deep-merge config.local.yaml over it, and validate.

    Raises :class:`ConfigError` with a clear message on any problem.
    """
    cfg_path = path or CONFIG_PATH
    if not cfg_path.exists():
        raise ConfigError(f"config.yaml not found at {cfg_path}")
    base = _read_yaml(cfg_path)
    local = load_local(local_path)
    merged = _deep_merge(base, local)
    try:
        return Config.model_validate(merged)
    except ValidationError as exc:
        where = "config.yaml + config.local.yaml" if local else "config.yaml"
        raise ConfigError(f"{where} failed validation:\n{exc}") from exc
