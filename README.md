# satisfactory-sprites

Turn a local **Satisfactory** install into true-to-scale orthographic blueprint **SVGs/PNGs**
(top / front / back / left / right) for dropping into Excalidraw, draw.io, or Miro.

This is a clean, standards-enforced rebuild of the pipeline. See
[`NEW_REPO_PLAN.md`](../NEW_REPO_PLAN.md) for the full plan and phase checklists, and
[`SPEC.md`](../SPEC.md) / [`PIPELINE.md`](../PIPELINE.md) for the deep design + step map.

> **Status:** Phase 0 (scaffolding) + Phase 2 (`doctor`) only. The pipeline stages are stubs.

## Quickstart

Full bootstrap (the few things doctor can't do for you) is in
[`GETTING_STARTED.md`](GETTING_STARTED.md). The short version:

```bash
brew install uv          # bootstrap prerequisite (needs Homebrew first)
./sat doctor             # check the machine + install what's missing (with confirmation)
./sat doctor --fix       # auto-run the safe fixes (downloads, brew installs) after confirming
```

`doctor` verifies (and can install) Docker, Blender, potrace, rsvg, the Oodle/zlib libs, and
**hard-stops if your installed game version does not match `config.yaml`** (`game.version`).

## Dev

```bash
./sat check              # ruff check + ruff format --check (+ csharpier in Phase 3)
./sat fix                # ruff --fix + ruff format
```

All tooling is Python (plus the C# extractor in Phase 3); there is no bash beyond the tiny
`./sat` launcher, which is itself Python.
