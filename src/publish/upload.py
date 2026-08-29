"""Publish stage (host, pure Python + the ``gh`` CLI).

``./sat upload <theme> <version>`` attaches the built deliverable zip
(``dist/<slug>/<slug>.zip``) to a GitHub Release as ``<slug>-<version>.zip``.

The release **tag** is ``v<version>``, so multiple themes (or re-runs) all land on the *one* release
page for a version:

  * The first upload for a version **creates** the release, pinned to the exact ``HEAD`` commit,
    with a placeholder title + body.
  * Later uploads leave the release's title / sha / body **untouched** and just attach (or, for the
    same asset name, ``--clobber``-replace) their own zip.

Because the release is pinned to ``HEAD``'s sha, ``HEAD`` must already exist on the remote. If it
doesn't, we stop and tell the user to ``git push`` first rather than pushing on their behalf.
"""

from __future__ import annotations

import contextlib
import shutil
import subprocess
import tempfile
from pathlib import Path

from src.cli import console as C
from src.cli.context import DIST_DIR
from src.common.theme import ThemeError, load_theme

REPO_ROOT = Path(__file__).resolve().parents[2]

PLACEHOLDER_NOTES = (
    "Orthographic, true-to-scale blueprint bundles for Satisfactory buildings.\n\n"
    "Each asset is a per-theme zip containing `svg/`, `png/`, a self-contained `preview.html`, "
    "and `metadata.json`."
)


class UploadError(Exception):
    """Raised when the upload can't proceed (missing zip/tooling, unpushed HEAD, gh failure)."""


def _gh(args: list[str], *, capture: bool = True) -> subprocess.CompletedProcess[str]:
    """Run ``gh <args>`` from the repo root; return the completed process (never raises on rc)."""
    return subprocess.run(
        ["gh", *args],
        cwd=REPO_ROOT,
        text=True,
        capture_output=capture,
        check=False,
    )


def _head_sha() -> str:
    """Full 40-char sha of the current ``HEAD``."""
    out = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if out.returncode != 0:
        raise UploadError(f"could not read HEAD sha: {out.stderr.strip()}")
    return out.stdout.strip()


def _commit_on_remote(sha: str) -> bool:
    """True if GitHub knows ``sha`` (i.e. HEAD has been pushed). Asks the API directly."""
    res = _gh(["api", f"repos/{{owner}}/{{repo}}/commits/{sha}", "--silent"])
    return res.returncode == 0


def _release_exists(tag: str) -> bool:
    """True if a release with ``tag`` already exists."""
    return _gh(["release", "view", tag]).returncode == 0


def _release_url(tag: str) -> str:
    """The browser URL for the release ``tag`` (empty string if it can't be resolved)."""
    res = _gh(["release", "view", tag, "--json", "url", "-q", ".url"])
    return res.stdout.strip() if res.returncode == 0 else ""


def run(theme: str, version: str) -> None:
    """Attach ``dist/<slug>/<slug>.zip`` to release ``v<version>`` as ``<slug>-<version>.zip``."""
    if shutil.which("gh") is None:
        raise UploadError("the GitHub CLI `gh` is not installed. See https://cli.github.com/.")

    try:
        slug = load_theme(theme).slug
    except ThemeError as exc:
        raise UploadError(str(exc)) from exc

    zip_src = DIST_DIR / slug / f"{slug}.zip"
    if not zip_src.is_file():
        raise UploadError(f"no built zip at {zip_src}. Run `./sat build --theme {theme}` first.")

    tag = f"v{version}"
    asset_name = f"{slug}-{version}.zip"

    if _release_exists(tag):
        C.console.print(f"[dim]Release [b]{tag}[/b] exists -- attaching[/] [b]{asset_name}[/b]")
    else:
        sha = _head_sha()
        if not _commit_on_remote(sha):
            raise UploadError(
                f"HEAD ({sha[:7]}) isn't on the remote, so the release can't pin to it.\n"
                f"  Push it first, e.g.  git push origin HEAD  (then re-run)."
            )
        C.console.print(f"[dim]Creating release [b]{tag}[/b] pinned to[/] [b]{sha[:7]}[/b]")
        res = _gh(
            [
                "release",
                "create",
                tag,
                "--target",
                sha,
                "--title",
                tag,
                "--notes",
                PLACEHOLDER_NOTES,
            ]
        )
        if res.returncode != 0:
            raise UploadError(f"`gh release create {tag}` failed:\n{res.stderr.strip()}")

    # Upload the zip under its versioned asset name (a temp copy so `gh` names the asset for us).
    with tempfile.TemporaryDirectory() as tmp:
        staged = Path(tmp) / asset_name
        shutil.copy2(zip_src, staged)
        res = _gh(["release", "upload", tag, str(staged), "--clobber"])
        if res.returncode != 0:
            raise UploadError(f"`gh release upload {tag}` failed:\n{res.stderr.strip()}")

    url = _release_url(tag)
    size_kib = zip_src.stat().st_size // 1024
    C.console.print(
        f"\n[green]Uploaded[/] [b]{asset_name}[/b] [dim]({size_kib} KiB)[/] -> release [b]{tag}[/b]"
    )
    if url:
        C.console.print(f"  [dim]{url}[/]")
        with contextlib.suppress(OSError):
            subprocess.run(["pbcopy"], input=url, text=True, check=False)
