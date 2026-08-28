"""Stage 1 -- the only game-reliant code: extract meshes + port data from the install.

The heavy lifting is a .NET CLI (``dotnet/``, built on CUE4Parse) run inside a linux/amd64
Docker container (for Oodle). This package is the Python host driver that builds the image,
mounts the game read-only, and routes outputs into ``build/01-extract/``.
"""
