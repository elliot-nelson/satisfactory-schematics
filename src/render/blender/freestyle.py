"""Freestyle SCRIPT-mode style module: capture visible feature-edge strokes as 2D polylines.

Loaded as a Freestyle module by ``entry.py`` (``fs.mode = "SCRIPT"``) and executed inside
Freestyle's own environment during each Blender render. It selects the blueprint feature edges
(silhouette / border / crease), keeps only fully-visible ones (Quantitative Invisibility == 0 =
hidden-line removal), chains them into strokes, and appends each stroke's image-space vertices
(pixels, origin BOTTOM-left -- ``finalize`` flips Y) as a whitespace-separated ``x,y x,y ...`` line
to the file named by the env var ``SF_SVG_PATHS``.

These strokes are theme-independent (pure colorless polylines), so the render runs once and every
theme's SVG is assembled from them downstream (see ``src/finalize/``). Ported 1:1 from the proven
standalone ``svg_style.py``.
"""

import os

from freestyle.chainingiterators import ChainSilhouetteIterator
from freestyle.predicates import (
    AndUP1D,
    NotUP1D,
    OrUP1D,
    QuantitativeInvisibilityUP1D,
    TrueUP1D,
    pyNatureUP1D,
)
from freestyle.types import Nature, Operators, StrokeShader


class SVGPathWriter(StrokeShader):
    def shade(self, stroke):
        out = os.environ.get("SF_SVG_PATHS")
        if not out:
            return
        pts = [f"{sv.point[0]:.2f},{sv.point[1]:.2f}" for sv in stroke]
        if len(pts) >= 2:
            with open(out, "a") as f:  # noqa: PTH123 (stdlib-only inside Blender)
                f.write(" ".join(pts) + "\n")


_nature = OrUP1D(
    pyNatureUP1D(Nature.SILHOUETTE),
    OrUP1D(pyNatureUP1D(Nature.BORDER), pyNatureUP1D(Nature.CREASE)),
)
_upred = AndUP1D(QuantitativeInvisibilityUP1D(0), _nature)

Operators.select(_upred)
Operators.bidirectional_chain(ChainSilhouetteIterator(), NotUP1D(_upred))
Operators.create(TrueUP1D(), [SVGPathWriter()])
