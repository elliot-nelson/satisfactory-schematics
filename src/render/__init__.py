"""Stage 3 -- render. Drives Blender to produce theme-independent orthographic rasters (and,
later, Freestyle strokes + a projection manifest) from the extracted ``.glb`` models.

The Blender-side code lives in ``blender/`` and runs inside Blender's own interpreter; this
package is the host driver that locates Blender and spawns it per model.
"""
