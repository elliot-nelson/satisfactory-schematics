# Vendored: CUE4Parse (patched for Satisfactory)

This is a **trimmed, patched snapshot** of [CUE4Parse](https://github.com/FabianFG/CUE4Parse) —
the Unreal Engine asset parser behind [FModel]. Our `.NET` extractor
(`../../src/extract/dotnet/`) references it as a project dependency to read meshes and blueprint
data out of a local Satisfactory install.

It's vendored (rather than pulled from NuGet or a submodule) because:

- We need a **source** patch (see below) — you can't patch a NuGet binary, and CUE4Parse's
  canonical distribution is source (FModel builds it from a submodule).
- Vendoring keeps the build **reproducible and offline**: upstream moves fast and could
  force-push or delete; a checked-in snapshot can't break out from under us.

## Upstream source

| | |
|---|---|
| Repo | `https://github.com/FabianFG/CUE4Parse` |
| Commit | `7ff8701b54ff1979f22576006cbee26276e5637c` (`FClothLODData struct`, 2026-05-15) |
| License | Apache-2.0 (see `LICENSE`, `NOTICE`, `UPSTREAM-README.md`) |

## What we trimmed (vs. a full checkout)

Dropped to shrink 213 MB → ~10 MB, none of which we compile:

- `.git/` history (144 MB)
- `CUE4Parse-Natives/` — the C++ (ACL/Oodle) natives. They are only built by the cmake
  `Build-Natives` MSBuild target, which our patch disables via `CUE4PARSE_SKIP_NATIVE=true`
  (there is **no** `ProjectReference` to them). Oodle/zlib decompression is instead provided
  at runtime by prebuilt Linux libs baked into the Docker image.
- `CUE4Parse.Tests/`, `CUE4Parse.Example/`, `.github/`, `.sln`, all `bin/`/`obj/`.

## Patch we applied

The **entire** delta from pristine upstream is in [`patches/sf-extract.patch`](patches/sf-extract.patch)
— two functional changes (each modified file also gets a short "modified for satisfactory-schematics"
provenance header, per Apache-2.0 §4(b)):

1. **`CUE4Parse/MappingsProvider/Usmap/UsmapProperties.cs`** — the load-bearing fix. Satisfactory's
   shipped `FactoryGame.usmap` encodes `OptionalProperty` as a **leaf** (no inner type). Upstream
   groups it with `Array`/`Set` and reads an inner type, which consumes one extra byte and desyncs
   the whole usmap struct table → `IndexOutOfRange`. We treat `OptionalProperty` as a leaf.
   (This is independent of the UE/EGame version we pass to the provider — usmap parsing keys only
   on the usmap's own format version.)
2. **`CUE4Parse/CUE4Parse.csproj`** — gate the cmake `Build-Natives` target on
   `CUE4PARSE_SKIP_NATIVE != true` so we can skip the C++ build we don't use.

The snapshot in this folder **already has the patch applied.** The patch file is kept for
provenance and so the delta stays auditable.

## ⚠️ This patch is tied to specific versions — revisit it on any upgrade

The `OptionalProperty` fix is a **workaround for one specific pairing**, not a permanent truth:

| Pinned to | Value |
|---|---|
| Satisfactory game version | **`1.2.4.0`** (UE **5.6.1**) — see `config.yaml` `game.version` |
| CUE4Parse commit | **`7ff8701`** (2026-05-15) |

The need for the patch depends on **both**:

- **Game version** — the fix exists because Coffee Stain's `FactoryGame.usmap` for this build writes
  `OptionalProperty` without an inner type. A future game update could ship a spec-compliant usmap,
  which would make the patch **unnecessary** (and, if upstream also changes, potentially *harmful* —
  skipping an inner type that's now present would re-introduce a desync).
- **CUE4Parse version** — upstream could add first-class handling for this usmap encoding, at which
  point our change becomes redundant or conflicts with theirs.

**So, whenever you bump either version:**

1. Re-run extraction on a machine that still has the patch. If it still works, fine.
2. Also try **reverting** the patch (`git apply -R patches/sf-extract.patch`) and re-extracting — if it
   now works unpatched, **drop the patch** and update this file.
3. If bumping CUE4Parse, re-apply `patches/sf-extract.patch`; a failing hunk is a signal that upstream
   touched this code and you must re-validate by hand.

Symptom that the patch is needed but missing: `IndexOutOfRange` in `ReadName` while parsing the usmap
struct table (extraction aborts before exporting any mesh).

## Verify / re-derive against a fresh upstream checkout

```sh
git clone https://github.com/FabianFG/CUE4Parse
cd CUE4Parse && git checkout 7ff8701b54ff1979f22576006cbee26276e5637c
git apply /path/to/vendor/cue4parse/patches/sf-extract.patch   # applies cleanly (-p1)
```

To bump upstream: check out the new commit, `git apply` this patch (re-roll it if a hunk
fails — a failure is a signal to re-validate against the new version), re-run the trim, and
update the commit hash above.
