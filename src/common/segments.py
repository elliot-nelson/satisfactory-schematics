"""Expand the segment catalog into concrete render jobs.

Belts and pipes are spline tiles in game, so there's no single "belt" mesh to draw -- we synthesise
the diagram pieces at render time: a few straight runs plus two 90-degree corners. Steel beams
extrude along their local Z, so we tile them the same way but down that axis. Pipe junctions and the
beam connector cube are ordinary static meshes, rendered as-is. This lives here (not buried in the
render driver) so the preview stage can reuse it to bucket each piece into the right category.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass

from src.common.buildings import Catalog, Segment

# 90-degree corner variants for belts/pipes: suffix -> centerline radius in meters.
CORNER_RADII: OrderedDict[str, float] = OrderedDict([("corner", 2.0), ("tight_corner", 1.0)])

# Which preview bucket each segment kind lands in (keys match preview CATEGORY_META).
_CATEGORY = {
    "belt": "logistics",
    "pipe": "logistics",
    "junction": "logistics",
    "beam": "architecture",
    "connector-cube": "architecture",
}


@dataclass(frozen=True)
class SegmentJob:
    """One rendered output derived from a source segment mesh."""

    name: str  # output stem, e.g. belt_4m / belt_corner / painted_beam_8m
    source: str  # extracted glb stem, e.g. belt_segment
    kind: str  # belt / pipe / beam / junction / connector-cube
    category: str
    tile_length: float | None = None  # meters, straight run
    corner_radius: float | None = None  # meters, 90-degree bend
    tile_axis: str = "x"


def _prefix(seg: Segment) -> str:
    """Belts/pipes are ``belt_segment`` / ``pipe_segment`` but the pieces read as belt_*/pipe_*.

    Beams keep their own name so painted vs. cross stay distinct (painted_beam_*, cross_beam_*).
    """
    return seg.name[: -len("_segment")] if seg.name.endswith("_segment") else seg.name


def segment_jobs(catalog: Catalog, lengths: list[int]) -> list[SegmentJob]:
    """Flatten the catalog's segments into the individual pieces we render."""
    jobs: list[SegmentJob] = []
    for seg in catalog.segments:
        kind = seg.kind or ""
        category = _CATEGORY.get(kind, "other")
        if kind in ("belt", "pipe"):
            pre = _prefix(seg)
            for length in lengths:
                jobs.append(
                    SegmentJob(
                        f"{pre}_{length}m", seg.name, kind, category, tile_length=float(length)
                    )
                )
            for suffix, radius in CORNER_RADII.items():
                jobs.append(
                    SegmentJob(f"{pre}_{suffix}", seg.name, kind, category, corner_radius=radius)
                )
        elif kind == "beam":
            for length in lengths:
                jobs.append(
                    SegmentJob(
                        f"{seg.name}_{length}m",
                        seg.name,
                        kind,
                        category,
                        tile_length=float(length),
                        tile_axis="z",
                    )
                )
        else:  # junction, connector-cube: render the mesh as-is
            jobs.append(SegmentJob(seg.name, seg.name, kind, category))
    return jobs
