"""The ``doctor`` routine: bring a brand-new machine up to spec.

Assumes (almost) nothing is installed. Each check reports a status and, where possible, an
auto-runnable or manual remediation. The **game-version gate** is special: on a mismatch it
hard-stops and offers no fix, because the extractor is pinned to exactly one game/engine build
(SPEC.md 12.1).

macOS / Homebrew first; structured so Linux remediations can slot in later.
"""

from __future__ import annotations

import gzip
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from rich.table import Table

from src.cli import console as C
from src.cli.config import Config, ConfigError, load_config, update_local
from src.cli.context import DOCTOR_DIR, REPO_ROOT, ensure


class Status(StrEnum):
    OK = "ok"
    WARN = "warn"
    FAIL = "fail"
    SKIP = "skip"
    PENDING = "pending"


_GLYPH = {
    Status.OK: "[green]OK[/]",
    Status.WARN: "[yellow]WARN[/]",
    Status.FAIL: "[red]FAIL[/]",
    Status.SKIP: "[dim]SKIP[/]",
    Status.PENDING: "[cyan]PENDING[/]",
}


@dataclass
class Fix:
    """A remediation. ``run`` returns True on success; ``manual`` is fallback guidance."""

    description: str
    run: Callable[[], bool] | None = None
    manual: str | None = None


@dataclass
class Check:
    name: str
    status: Status
    detail: str = ""
    fix: Fix | None = None
    required: bool = True  # whether an unresolved FAIL should make doctor exit non-zero


# --------------------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------------------

MACOS = platform.system() == "Darwin"


def _which(name: str) -> str | None:
    return shutil.which(name)


def _run(cmd: list[str], *, timeout: int = 20) -> tuple[int, str]:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, str(exc)
    return proc.returncode, (proc.stdout + proc.stderr).strip()


def _brew_fix(pkg: str, *, cask: bool = False) -> Fix:
    """Build a Homebrew remediation for ``pkg``."""
    args = ["brew", "install", *(["--cask"] if cask else []), pkg]
    cmd_str = " ".join(args)

    def run() -> bool:
        if not _which("brew"):
            C.err_console.print("  brew is not installed; see https://brew.sh")
            return False
        C.console.print(f"  running: [cyan]{cmd_str}[/]")
        code, out = _run(args, timeout=1800)
        if code != 0:
            C.err_console.print(f"  {out}")
        return code == 0

    return Fix(description=cmd_str, run=(run if MACOS else None), manual=cmd_str)


# --------------------------------------------------------------------------------------
# Individual checks
# --------------------------------------------------------------------------------------


def check_python_uv() -> Check:
    py = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    uv = _which("uv")
    if not uv:
        return Check(
            "python + uv",
            Status.WARN,
            f"Python {py}; uv not found",
            Fix("install uv", manual="brew install uv"),
        )
    _, ver = _run([uv, "--version"])
    return Check("python + uv", Status.OK, f"Python {py}; {ver}")


def check_config(cfg: Config | None, err: str | None) -> Check:
    if cfg is None:
        return Check("config.yaml", Status.FAIL, err or "invalid")
    return Check(
        "config.yaml",
        Status.OK,
        f"game {cfg.game.version} / UE {cfg.game.engineVersion}",
    )


def _common_game_dirs() -> list[Path]:
    """Common Satisfactory install locations across macOS / Windows / Linux."""
    home = Path.home()
    dirs = [
        REPO_ROOT / "game",
        REPO_ROOT.parent / "game",
        # macOS Steam
        home / "Library/Application Support/Steam/steamapps/common/Satisfactory",
        # Linux Steam
        home / ".steam/steam/steamapps/common/Satisfactory",
        home / ".local/share/Steam/steamapps/common/Satisfactory",
    ]
    # Windows Steam / Epic (harmless no-ops on other OSes).
    for drive in ("C:", "D:", "E:"):
        dirs += [
            Path(rf"{drive}\Program Files (x86)\Steam\steamapps\common\Satisfactory"),
            Path(rf"{drive}\SteamLibrary\steamapps\common\Satisfactory"),
            Path(rf"{drive}\Program Files\Epic Games\SatisfactoryEarlyAccess"),
            Path(rf"{drive}\Program Files\Epic Games\SatisfactoryExperimental"),
        ]
    return dirs


def resolve_game_dir(cfg: Config) -> tuple[Path | None, str]:
    """Find the install and report where it came from.

    An **explicitly configured** path (``config.local.yaml``/``config.yaml`` ``game.path`` or
    ``$SAT_GAME_DIR``) is honored even when it doesn't exist -- it comes back with a
    ``*-missing`` source so doctor reports it and never silently overwrites your choice.
    Auto-detection of a common location only happens when nothing is configured.

    Returns ``(path, source)`` with source in: ``config``, ``config-missing``, ``env``,
    ``env-missing``, ``detected``, ``none``.
    """
    if cfg.game.path:
        p = Path(cfg.game.path).expanduser()
        return (p, "config") if p.is_dir() else (p, "config-missing")
    if env := os.environ.get("SAT_GAME_DIR"):
        p = Path(env).expanduser()
        return (p, "env") if p.is_dir() else (p, "env-missing")
    for c in _common_game_dirs():
        if c.is_dir():
            return c, "detected"
    return None, "none"


def check_game_path(cfg: Config, game_dir: Path | None, source: str) -> Check:
    if source in ("config-missing", "env-missing"):
        where = (
            "$SAT_GAME_DIR" if source == "env-missing" else "game.path (config/config.local.yaml)"
        )
        return Check(
            "game install",
            Status.FAIL,
            f"configured path does not exist: {game_dir} (from {where}). "
            f"Fix it, or clear it to re-enable auto-detection.",
        )
    if game_dir is None:
        return Check(
            "game install",
            Status.FAIL,
            "not found in config or any common location (see GETTING_STARTED.md 3)",
            Fix(
                "point at your install",
                manual=(
                    "set game.path in config/config.local.yaml, or "
                    "export SAT_GAME_DIR=/path/to/Satisfactory"
                ),
            ),
        )
    missing = [rel for rel in cfg.game.requires if not (game_dir / rel).exists()]
    if missing:
        return Check(
            "game install",
            Status.FAIL,
            f"{game_dir} is missing: {', '.join(missing)}",
        )
    note = (
        " (auto-detected -> cached to config/config.local.yaml)"
        if source == "detected"
        else f" (from {source})"
    )
    return Check("game install", Status.OK, f"{game_dir}{note}")


def _read_version_file(game_dir: Path) -> dict[str, Any] | None:
    hits = list((game_dir / "Engine/Binaries/Win64").glob("*.version"))
    if not hits:
        return None
    try:
        return json.loads(hits[0].read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None


def check_game_version(cfg: Config, game_dir: Path | None) -> Check:
    """The hard gate. A mismatch fails with no fix -- we can't change the user's game."""
    if game_dir is None:
        return Check("game version", Status.SKIP, "no game install to check")
    data = _read_version_file(game_dir)
    if data is None:
        return Check(
            "game version",
            Status.FAIL,
            "could not read Engine/Binaries/Win64/*.version",
        )
    found_game = str(data.get("GameVersion", "?"))
    found_engine = (
        f"{data.get('MajorVersion')}.{data.get('MinorVersion')}.{data.get('PatchVersion')}"
    )
    want_game = cfg.game.version
    want_engine = cfg.game.engineVersion
    if found_game == want_game and found_engine == want_engine:
        return Check("game version", Status.OK, f"{found_game} (UE {found_engine})")
    return Check(
        "game version",
        Status.FAIL,
        (
            f"MISMATCH: installed {found_game} (UE {found_engine}); "
            f"pinned {want_game} (UE {want_engine}). Extraction will misread meshes -- "
            f"update the game to match, or bump config.yaml + re-validate CUE4Parse (SPEC 12.1)."
        ),
        required=True,
    )


def check_docker() -> Check:
    if not _which("docker"):
        return Check(
            "docker",
            Status.FAIL,
            "not installed (needed for mesh extraction)",
            _brew_fix("docker", cask=True),
        )
    code, _ = _run(["docker", "info"], timeout=15)
    if code != 0:
        return Check(
            "docker",
            Status.WARN,
            "installed but daemon not running -- start Docker Desktop",
            Fix("start Docker", manual="open -a Docker  # then wait for it to be ready"),
        )
    _, ver = _run(["docker", "--version"])
    return Check("docker", Status.OK, ver)


def check_blender(cfg: Config) -> Check:
    want = cfg.tools.blender.version
    binary = (
        os.environ.get(cfg.tools.blender.env)
        or _which("blender")
        or ("/Applications/Blender.app/Contents/MacOS/Blender" if MACOS else None)
    )
    if not binary or not Path(binary).exists():
        return Check(
            "blender",
            Status.FAIL,
            f"not found (want {want}.x); set ${cfg.tools.blender.env} or install",
            _brew_fix("blender", cask=True),
        )
    _, out = _run([str(binary), "--version"], timeout=30)
    m = re.search(r"Blender\s+(\d+)\.(\d+)", out)
    if not m:
        return Check("blender", Status.WARN, f"found {binary} (version unknown)")
    found = f"{m.group(1)}.{m.group(2)}"
    if found != want:
        return Check(
            "blender",
            Status.WARN,
            f"found {found}, expected {want} (Freestyle behaviors are version-sensitive)",
        )
    return Check("blender", Status.OK, f"{found} at {binary}")


def check_cli_tool(name: str, brew_pkg: str, *, required: bool, purpose: str) -> Check:
    if _which(name):
        _, ver = _run([name, "--version"])
        first = ver.splitlines()[0] if ver else name
        return Check(name, Status.OK, first)
    status = Status.FAIL if required else Status.WARN
    return Check(name, status, f"not installed ({purpose})", _brew_fix(brew_pkg), required=required)


def check_dotnet(cfg: Config) -> Check:
    if _which("dotnet"):
        _, ver = _run(["dotnet", "--version"])
        return Check("dotnet (optional)", Status.OK, ver, required=False)
    return Check(
        "dotnet (optional)",
        Status.SKIP,
        "not installed; only needed for native extractor dev (docker path needs none)",
        _brew_fix("dotnet"),
        required=False,
    )


def _download_fix(
    url: str, dest: Path, *, gunzip: bool = False, zip_entry: str | None = None
) -> Fix:
    def run() -> bool:
        ensure(dest.parent)
        C.console.print(f"  downloading {url}")
        try:
            tmp, _ = urllib.request.urlretrieve(url)
        except OSError as exc:
            C.err_console.print(f"  download failed: {exc}")
            return False
        try:
            if zip_entry:
                with zipfile.ZipFile(tmp) as zf:
                    dest.write_bytes(zf.read(zip_entry))
            elif gunzip:
                with gzip.open(tmp, "rb") as gz:
                    dest.write_bytes(gz.read())
            else:
                shutil.copyfile(tmp, dest)
        except (OSError, KeyError, zipfile.BadZipFile) as exc:
            C.err_console.print(f"  extract failed: {exc}")
            return False
        return dest.exists()

    return Fix(description=f"download -> {dest.name}", run=run)


def check_native_libs(cfg: Config) -> Check:
    """Oodle + zlib libs baked into the extractor image (SPEC 6.4). Auto-downloadable."""
    libs = DOCTOR_DIR / "libs"
    oodle = libs / "liboodle-data-shared.so"
    zlib = libs / "libz-ng.so"
    have = oodle.exists() and zlib.exists()
    if have:
        return Check("oodle + zlib libs", Status.OK, str(libs), required=False)

    def run_all() -> bool:
        ok = True
        if cfg.extractor.oodle and not oodle.exists():
            ok &= _download_fix(
                cfg.extractor.oodle.url, oodle, zip_entry=cfg.extractor.oodle.entry
            ).run()  # type: ignore[union-attr]
        if cfg.extractor.zlib and not zlib.exists():
            ok &= _download_fix(cfg.extractor.zlib.url, zlib, gunzip=True).run()  # type: ignore[union-attr]
        return ok

    return Check(
        "oodle + zlib libs",
        Status.WARN,
        "not downloaded yet (baked into the extractor image at Phase 3)",
        Fix("download Oodle + zlib", run=run_all),
        required=False,
    )


def check_extractor_ready() -> Check:
    """Vendored+patched CUE4Parse and the sf-extract image."""
    usmap_patch = REPO_ROOT / "vendor/cue4parse/CUE4Parse/MappingsProvider/Usmap/UsmapProperties.cs"
    if not usmap_patch.exists():
        return Check(
            "extractor (CUE4Parse)",
            Status.PENDING,
            "vendor/cue4parse missing (see vendor/cue4parse/README.md)",
            required=False,
        )
    # Sentinel: the OptionalProperty-as-leaf patch must be present, or extraction desyncs.
    if "sf-extract: Satisfactory" not in usmap_patch.read_text(encoding="utf-8"):
        return Check(
            "extractor (CUE4Parse)",
            Status.WARN,
            "vendored but OptionalProperty patch missing -- re-apply patches/sf-extract.patch",
            required=False,
        )
    code, _ = _run(["docker", "image", "inspect", "sf-extract"], timeout=15)
    if code != 0:
        return Check(
            "extractor (CUE4Parse)",
            Status.WARN,
            "vendored but sf-extract image not built (SF_REBUILD=1 ./schematic extract)",
            required=False,
        )
    return Check("extractor (CUE4Parse)", Status.OK, "vendored + image built", required=False)


def check_precommit() -> Check:
    hook = REPO_ROOT / ".git/hooks/pre-commit"
    if hook.exists():
        return Check("pre-commit hooks", Status.OK, "installed", required=False)

    def run() -> bool:
        if not _which("pre-commit") and not _which("uv"):
            return False
        cmd = (
            ["pre-commit", "install"]
            if _which("pre-commit")
            else ["uv", "run", "pre-commit", "install"]
        )
        code, out = _run(cmd, timeout=120)
        if code != 0:
            C.err_console.print(f"  {out}")
        return code == 0

    return Check(
        "pre-commit hooks",
        Status.WARN,
        "not installed",
        Fix("pre-commit install", run=run),
        required=False,
    )


# --------------------------------------------------------------------------------------
# Runner
# --------------------------------------------------------------------------------------


def _collect(cfg: Config | None, cfg_err: str | None) -> list[Check]:
    checks: list[Check] = [check_python_uv(), check_config(cfg, cfg_err)]
    if cfg is None:
        return checks
    game_dir, source = resolve_game_dir(cfg)
    game_path_check = check_game_path(cfg, game_dir, source)
    # Cache ONLY a freshly auto-detected, valid install (source == "detected"). An explicitly
    # configured path -- even an invalid one -- is never overwritten: doctor reports it and
    # leaves the user's choice intact.
    if source == "detected" and game_dir is not None and game_path_check.status is Status.OK:
        update_local({"game": {"path": str(game_dir.resolve())}})
    # Only version-check a usable install; otherwise the version row would just echo the
    # path failure. A valid game path yields status OK above.
    usable_dir = game_dir if game_path_check.status is Status.OK else None
    checks += [
        game_path_check,
        check_game_version(cfg, usable_dir),
        check_docker(),
        check_blender(cfg),
        check_cli_tool(
            "potrace", cfg.tools.potrace.brew or "potrace", required=True, purpose="SVG fill trace"
        ),
        check_cli_tool(
            cfg.tools.rsvg.bin or "rsvg-convert",
            cfg.tools.rsvg.brew or "librsvg",
            required=False,
            purpose="optional PNG rasterize",
        ),
        check_dotnet(cfg),
        check_native_libs(cfg),
        check_extractor_ready(),
        check_precommit(),
    ]
    return checks


def _render_table(checks: list[Check]) -> None:
    table = Table(title="schematic doctor", show_lines=False, expand=True)
    table.add_column("Check", style="bold", no_wrap=True)
    table.add_column("Status", no_wrap=True)
    table.add_column("Detail", overflow="fold")
    for c in checks:
        table.add_row(c.name, _GLYPH[c.status], c.detail)
    C.console.print(table)


def _apply_fixes(checks: list[Check], *, auto: bool) -> None:
    fixable = [c for c in checks if c.status in (Status.FAIL, Status.WARN) and c.fix]
    if not fixable:
        return
    C.rule("Remediations")
    for c in fixable:
        assert c.fix is not None
        if c.fix.run is None:
            C.console.print(f"[yellow]{c.name}[/]: {c.fix.manual or c.fix.description}")
            continue
        proceed = auto or C.confirm(f"{c.name}: run '{c.fix.description}'?", default=False)
        if not proceed:
            C.console.print(
                f"[dim]{c.name}: skipped[/] (manual: {c.fix.manual or c.fix.description})"
            )
            continue
        ok = c.fix.run()
        C.console.print(f"  -> {'[green]done[/]' if ok else '[red]failed[/]'}")


def _cache(checks: list[Check]) -> None:
    ensure(DOCTOR_DIR)
    payload = [{"name": c.name, "status": c.status.value, "detail": c.detail} for c in checks]
    (DOCTOR_DIR / "doctor.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")


def run_doctor(*, fix: bool = False) -> int:
    """Run all checks, optionally apply fixes, cache results. Returns a process exit code."""
    cfg: Config | None = None
    cfg_err: str | None = None
    try:
        cfg = load_config()
    except ConfigError as exc:
        cfg_err = str(exc)

    checks = _collect(cfg, cfg_err)
    _render_table(checks)

    # The game-version gate is fatal and un-fixable: surface it prominently.
    version_check = next((c for c in checks if c.name == "game version"), None)
    if version_check and version_check.status is Status.FAIL and "MISMATCH" in version_check.detail:
        C.err_console.print(f"\n[red bold]Blocked:[/] {version_check.detail}")

    _apply_fixes(checks, auto=fix)
    if fix:
        # Re-run to reflect what got fixed.
        checks = _collect(cfg, cfg_err)
        C.rule("After fixes")
        _render_table(checks)

    _cache(checks)

    unresolved = [c for c in checks if c.required and c.status is Status.FAIL]
    if unresolved:
        C.err_console.print(
            f"\n[red]{len(unresolved)} required check(s) failing:[/] "
            + ", ".join(c.name for c in unresolved)
        )
        return 1
    C.console.print("\n[green]doctor: all required checks passing.[/]")
    return 0
