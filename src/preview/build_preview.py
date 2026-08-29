"""Build the theme preview: a standalone dark viewer (``preview.html``) + a machine-readable twin
(``preview.json``).

For the selected theme it scans the finalized SVGs (``build/04-svg/<slug>/``), pulls per-view
pixel/meter dimensions from the render manifests, groups builds into sections using each building's
``category`` from ``config/buildings.yaml`` (retiring the old hand-kept ``categories.json`` --
anything rendered but not in the catalog lands in a trailing "Other" section), and writes:

  * ``preview.html`` -- a single self-contained page (inline CSS + **inlined SVGs**, no external
    deps or build step): a sticky sidebar of jump links + a dark gallery with each drawing on an
    eggshell card, plus a click-to-zoom lightbox. Being self-contained, it renders identically from
    ``build/`` now and from ``dist/`` after the bundle stage copies it.
  * ``preview.json`` -- theme look + categories + per-build manifest & (relative) asset paths, so a
    future user-facing app can render its own viewer without re-deriving any of this.

Ported from the old ``tools/build_preview.py``; the HTML/CSS live in ``templates/``.
"""

from __future__ import annotations

import base64
import datetime
import json
import re
from collections import OrderedDict, defaultdict
from pathlib import Path
from typing import Any

from src.cli import console as C
from src.cli.config import Config
from src.cli.context import PNG_DIR, PREVIEW_DIR, RENDER_DIR, SVG_DIR, ensure
from src.common.buildings import Catalog, load_catalog
from src.common.plan import BuildPlan, StageError
from src.common.theme import Theme, ThemeError, load_theme

MANIFEST_DIR = RENDER_DIR / "manifests"
TEMPLATES = Path(__file__).resolve().parent / "templates"
VIEW_ORDER = ["top", "front", "back", "left", "right"]

# Display metadata for the known catalog categories (name + blurb + order). Categories not listed
# here (or the catch-all "other") get a title-cased name and land after these, so nothing vanishes.
CATEGORY_META: OrderedDict[str, dict[str, str]] = OrderedDict(
    [
        (
            "production",
            {"name": "Production", "blurb": "Machines that convert resources into parts."},
        ),
        (
            "logistics",
            {
                "name": "Logistics",
                "blurb": "Belts, pipes, and the pieces that route items and fluids.",
            },
        ),
        (
            "architecture",
            {"name": "Architecture", "blurb": "Structural steel beams and connectors."},
        ),
    ]
)


def prettify(stem: str) -> str:
    """``belt_tight_corner`` -> 'Belt Tight Corner'; ``cross_beam_8m`` -> 'Cross Beam 8m'."""
    return " ".join(p if re.fullmatch(r"\d+m", p) else p.capitalize() for p in stem.split("_"))


def _view_key(v: str) -> tuple[int, str]:
    return (VIEW_ORDER.index(v) if v in VIEW_ORDER else len(VIEW_ORDER), v)


def _esc(s: object) -> str:
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _fmt_bbox(bbox: dict[str, float] | None) -> str:
    if not bbox:
        return ""
    try:
        return f"{bbox['x']:.1f} \u00d7 {bbox['y']:.1f} \u00d7 {bbox['z']:.1f} m"
    except (KeyError, TypeError):
        return ""


def _load_manifest(stem: str) -> dict[str, Any]:
    path = MANIFEST_DIR / f"{stem}.json"
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def collect_builds(
    svg_dir: Path, png_dir: Path, only: set[str]
) -> OrderedDict[str, dict[str, Any]]:
    """Group ``<stem>_<view>.svg`` files per build, enriched with manifest dimensions."""
    groups: OrderedDict[str, dict[str, str]] = OrderedDict()
    for f in sorted(p.name for p in svg_dir.glob("*.svg")):
        stem, _, view = f[:-4].rpartition("_")
        if not stem:
            stem, view = f[:-4], ""
        if only and stem not in only:
            continue
        groups.setdefault(stem, {})[view] = f

    builds: OrderedDict[str, dict[str, Any]] = OrderedDict()
    for stem in sorted(groups):
        man = _load_manifest(stem)
        man_views = {v.get("view"): v for v in man.get("views", [])}
        views = []
        for view in sorted(groups[stem], key=_view_key):
            svg_name = groups[stem][view]
            png_name = svg_name[:-4] + ".png"
            mv = man_views.get(view, {})
            views.append(
                {
                    "view": view or "-",
                    "svg": svg_name,
                    "png": png_name if (png_dir / png_name).is_file() else None,
                    "width_px": mv.get("width_px"),
                    "height_px": mv.get("height_px"),
                    "width_m": mv.get("width_m"),
                    "height_m": mv.get("height_m"),
                }
            )
        builds[stem] = {
            "label": prettify(stem),
            "source": man.get("source"),
            "ppm": man.get("ppm"),
            "grid_m": man.get("grid_m"),
            "bbox_m": man.get("bbox_m"),
            "clearance_m": man.get("clearance_m"),
            "views": views,
        }
    return builds


def build_sections(
    builds: OrderedDict[str, dict[str, Any]], catalog: Catalog
) -> list[tuple[dict[str, str], list[str]]]:
    """Order builds into ``[(category, [stem,...]), ...]`` by each building's catalog category."""
    cat_of = {b.name: b.category for b in catalog.buildings}
    order = [b.name for b in catalog.buildings]

    by_cat: dict[str, list[str]] = defaultdict(list)
    for stem in builds:
        by_cat[cat_of.get(stem, "other")].append(stem)

    def sort_stems(stems: list[str]) -> list[str]:
        return sorted(stems, key=lambda s: (order.index(s) if s in order else len(order), s))

    sections: list[tuple[dict[str, str], list[str]]] = []
    seen: set[str] = set()
    for cid, meta in CATEGORY_META.items():
        if by_cat.get(cid):
            sections.append(({"id": cid, **meta}, sort_stems(by_cat[cid])))
            seen.add(cid)
    for cid, stems in by_cat.items():
        if cid in seen or not stems:
            continue
        name = "Other" if cid == "other" else cid.capitalize()
        blurb = "Rendered but not yet categorized." if cid == "other" else ""
        sections.append(({"id": cid, "name": name, "blurb": blurb}, sort_stems(stems)))
    return sections


def _theme_dict(theme: Theme) -> dict[str, Any]:
    return {
        "slug": theme.slug,
        "name": theme.name,
        "lineColor": theme.lineColor,
        "fillColor": theme.fillColor,
        "fillAlpha": theme.fillAlpha,
        "lineWidth": theme.lineWidth,
        "jitter": theme.jitter,
        "highlightPorts": theme.highlightPorts,
        "inputPortColor": theme.inputPortColor,
        "outputPortColor": theme.outputPortColor,
        "showCollisionBoxTicks": theme.showCollisionBoxTicks,
        "collisionBoxColor": theme.collisionBoxColor,
    }


# ---- preview.json ---------------------------------------------------------


def write_json(
    out_json: Path,
    theme: Theme,
    sections: list[tuple[dict[str, str], list[str]]],
    builds: OrderedDict[str, dict[str, Any]],
) -> dict[str, int]:
    n_views = sum(len(b["views"]) for b in builds.values())
    cat_of = {s: c["id"] for c, stems in sections for s in stems}
    bmap: OrderedDict[str, Any] = OrderedDict()
    for stem, b in builds.items():
        bmap[stem] = {
            "label": b["label"],
            "category": cat_of.get(stem, "other"),
            "source": b["source"],
            "ppm": b["ppm"],
            "grid_m": b["grid_m"],
            "bbox_m": b["bbox_m"],
            "clearance_m": b["clearance_m"],
            "views": [
                {
                    "view": v["view"],
                    "svg": "svg/" + v["svg"],
                    "png": ("png/" + v["png"]) if v["png"] else None,
                    "width_px": v["width_px"],
                    "height_px": v["height_px"],
                    "width_m": v["width_m"],
                    "height_m": v["height_m"],
                }
                for v in b["views"]
            ],
        }
    doc = {
        "schema": "satisfactory.preview/1",
        "generated": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "theme": _theme_dict(theme),
        "counts": {"categories": len(sections), "buildings": len(builds), "views": n_views},
        "categories": [
            {"id": c["id"], "name": c["name"], "blurb": c["blurb"], "builds": list(stems)}
            for c, stems in sections
        ],
        "buildings": bmap,
    }
    out_json.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    return doc["counts"]


# ---- preview.html ---------------------------------------------------------


def _data_uri(svg_path: Path) -> str:
    """Inline an SVG file as a base64 ``data:`` URI so preview.html is fully self-contained."""
    b64 = base64.b64encode(svg_path.read_bytes()).decode("ascii")
    return f"data:image/svg+xml;base64,{b64}"


def _render_html(
    theme: Theme,
    sections: list[tuple[dict[str, str], list[str]]],
    builds: OrderedDict[str, dict[str, Any]],
    svg_dir: Path,
) -> str:
    side = []
    for c, stems in sections:
        links = "".join(
            f'<li><a href="#b-{s}" data-target="b-{s}">{_esc(builds[s]["label"])}</a></li>'
            for s in stems
        )
        side.append(
            f'<div class="side-cat"><div class="side-cat-h">{_esc(c["name"])}'
            f'<span class="side-cat-n">{len(stems)}</span></div><ul>{links}</ul></div>'
        )

    main = []
    for c, stems in sections:
        blds = []
        for s in stems:
            b = builds[s]
            cards = []
            for v in b["views"]:
                dims = f"{v['width_px']}\u00d7{v['height_px']} px" if v["width_px"] else ""
                src = _data_uri(svg_dir / v["svg"])
                cards.append(
                    f'<figure class="card"><div class="stage">'
                    f'<img loading="lazy" src="{src}" alt="{_esc(v["svg"])}" '
                    f'data-label="{_esc(b["label"])}" data-view="{_esc(v["view"])}" '
                    f'data-dims="{dims}"></div>'
                    f'<figcaption><span class="v">{_esc(v["view"])}</span>'
                    f'<span class="d">{dims}</span></figcaption></figure>'
                )
            bbox = _fmt_bbox(b["bbox_m"])
            meta = f" &middot; {bbox}" if bbox else ""
            blds.append(
                f'<section class="build" id="b-{s}"><div class="build-h">'
                f"<h3>{_esc(b['label'])}</h3>"
                f'<span class="build-meta">{len(b["views"])} views{meta}</span></div>'
                f'<div class="views">{"".join(cards)}</div></section>'
            )
        main.append(
            f'<section class="cat" id="cat-{c["id"]}"><header class="cat-h">'
            f"<h2>{_esc(c['name'])}</h2><p>{_esc(c['blurb'])}</p></header>{''.join(blds)}</section>"
        )

    css = (TEMPLATES / "preview.css").read_text(encoding="utf-8")
    html = (TEMPLATES / "preview.html").read_text(encoding="utf-8")
    n_views = sum(len(b["views"]) for b in builds.values())
    replacements = {
        "{{CSS}}": css,
        "{{ACCENT}}": _esc(theme.lineColor or "#38bdf8"),
        "{{TITLE}}": _esc(theme.name),
        "{{SLUG}}": _esc(theme.slug),
        "{{N_CATS}}": str(len(sections)),
        "{{N_BUILDS}}": str(len(builds)),
        "{{N_VIEWS}}": str(n_views),
        "{{SIDEBAR}}": "".join(side),
        "{{MAIN}}": "".join(main),
    }
    for token, value in replacements.items():
        html = html.replace(token, value)
    return html


# ---- stage entrypoint -----------------------------------------------------


def run(cfg: Config, plan: BuildPlan) -> None:
    """Assemble ``preview.html`` + ``preview.json`` for the selected theme."""
    try:
        theme = load_theme(plan.theme)
    except ThemeError as exc:
        raise StageError(str(exc)) from exc

    svg_dir = SVG_DIR / theme.slug
    if not svg_dir.is_dir() or not any(svg_dir.glob("*.svg")):
        raise StageError(
            f"no finalized SVGs at {svg_dir}. Run `./schematic build` (finalize) first."
        )

    catalog = load_catalog(cfg)
    builds = collect_builds(svg_dir, PNG_DIR / theme.slug, plan.only)
    sections = build_sections(builds, catalog)

    out_dir = ensure(PREVIEW_DIR / theme.slug)
    counts = write_json(out_dir / "preview.json", theme, sections, builds)
    (out_dir / "preview.html").write_text(
        _render_html(theme, sections, builds, svg_dir), encoding="utf-8"
    )

    C.console.print(
        f"\n[green]Preview complete[/] -> {out_dir / 'preview.html'}  "
        f"[dim]({counts['categories']} categories, {counts['buildings']} builds, "
        f"{counts['views']} views)[/]"
    )
