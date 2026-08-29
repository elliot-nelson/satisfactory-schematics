"""The prepare stage. Turn the raw game-derived files in ``build/01-extract/`` into the small,
normalized JSON the renderer reads, written to ``build/02-prepare/``:

    clearance.json     true in-game clearance box per building (from the docs dump)
    ports.json         normalized belt/pipe I/O ports (role, kind, pos, yaw)
    mesh_offsets.json  where the blueprint places each body mesh (+ optional annot fixup)

Pure Python, fully offline: it only reads ``build/01-extract/`` (never the game install) and is
driven entirely by the catalog (``config/buildings.yaml``), so the old hardcoded name maps are gone.
"""
