"""Bundle stage driver (host, pure Python).

Publish the selected theme's finished artifacts into its deliverable folder ``dist/<theme>/``:

    dist/<theme>/
      preview.html          <- the self-contained viewer (build/06-preview/<theme>/)
      metadata.json         <- the machine-readable twin (build/06-preview/<theme>/preview.json)
      svg/<name>_<view>.svg <- every finalized vector      (build/04-svg/<theme>/)
      png/<name>_<view>.png <- every rasterized view, if any (build/05-png/<theme>/)
      <theme>.zip           <- all of the above, zipped for sharing

``dist/`` is a pure mirror of the build outputs, so each run wipes and re-populates **only the
selected theme's** folder (``dist/<theme>/``) and leaves every other theme in ``dist/`` untouched.
"""

from __future__ import annotations

import shutil
import zipfile
from pathlib import Path

from src.cli import console as C
from src.cli.config import Config
from src.cli.context import DIST_DIR, PNG_DIR, PREVIEW_DIR, SVG_DIR, ensure
from src.common.plan import BuildPlan, StageError
from src.common.theme import ThemeError, load_theme


def _copy_glob(src_dir: Path, dst_dir: Path, pattern: str) -> int:
    """Copy every ``pattern`` file from ``src_dir`` into ``dst_dir``; return the count copied."""
    files = sorted(src_dir.glob(pattern)) if src_dir.is_dir() else []
    if not files:
        return 0
    ensure(dst_dir)
    for f in files:
        shutil.copy2(f, dst_dir / f.name)
    return len(files)


def _zip_dir(dest: Path, zip_path: Path) -> None:
    """Zip the staged ``dest`` tree into ``zip_path`` (relative arcnames; excludes the zip)."""
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(dest.rglob("*")):
            if path == zip_path or not path.is_file():
                continue
            zf.write(path, path.relative_to(dest).as_posix())


def run(cfg: Config, plan: BuildPlan) -> None:
    """Assemble ``dist/<theme>/`` from the finalized SVG/PNG + preview, then zip it."""
    try:
        theme = load_theme(plan.theme)
    except ThemeError as exc:
        raise StageError(str(exc)) from exc

    slug = theme.slug
    preview_src = PREVIEW_DIR / slug
    html_src = preview_src / "preview.html"
    json_src = preview_src / "preview.json"
    if not html_src.is_file() or not json_src.is_file():
        raise StageError(f"no preview at {preview_src}. Run `./schematic build` (preview) first.")

    dest = DIST_DIR / slug
    if dest.exists():  # clear ONLY this theme's dir, never touch other themes in dist/
        shutil.rmtree(dest)
    ensure(dest)

    n_svg = _copy_glob(SVG_DIR / slug, dest / "svg", "*.svg")
    n_png = _copy_glob(PNG_DIR / slug, dest / "png", "*.png")
    shutil.copy2(html_src, dest / "preview.html")
    shutil.copy2(json_src, dest / "metadata.json")

    zip_path = dest / f"{slug}.zip"
    _zip_dir(dest, zip_path)

    png_note = f", {n_png} PNG" if n_png else ""
    C.console.print(
        f"\n[green]Bundle complete[/] -> {dest}  "
        f"[dim]({n_svg} SVG{png_note}, preview.html, metadata.json)[/]"
    )
    C.console.print(f"  [dim]zipped ->[/] {zip_path.name}  ({zip_path.stat().st_size // 1024} KiB)")
