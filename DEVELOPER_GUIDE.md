# Developer Guide

Want to make your own theme, or tweak how the schematics look? Feel free to clone the repo and hack away!

> [!IMPORTANT]
>
> This repository does **not** contain any Satisfactory assets. To use this tool you need a copy of
> Satisfactory installed locally, matching the version pinned in
> [`config/config.yaml`](config/config.yaml) (currently **game `1.2.4.0`, engine UE `5.6.1`**).

A quick heads-up: this was all developed on **macOS (Apple Silicon)**, so it may make a few
assumptions that trip up Windows or Linux. If you hit a snag and have a fix, I'd happily take a PR.
And if you're on a newer version of Satisfactory, the
[Satisfactory Modding wiki](https://docs.ficsit.app/satisfactory-modding/latest/index.html) may be helpful in identifying new dependency versions.

## Quickstart

The short version, once you're set up:

```bash
./schematic doctor     # check the machine + install anything missing (with confirmation)
./schematic extract    # pull mesh + game data out of your local Satisfactory install
./schematic build      # do everything else -> dist/<theme>/
```

- `doctor` finds (and offers to install) the dependencies: Docker, Blender, potrace, rsvg, the
  Oodle/zlib libs, etc.
- `extract` is the one step that needs the game (and is the slowest step).
- `build` turns the extracted data into finished SVGs, PNGs, a preview page, and a shareable ZIP.

That's the happy path. The rest of this guide covers the one-time bootstrap and what to do when
something needs a human.

## Bootstrap

`doctor` is a Python program that runs through `uv`, so a handful of things have to exist before it
can even start. Do these once, in order:

> ![NOTE]
>
> On Windows or Linux? Skip steps 1-2 and follow OS instructions for installing `uv`.

1. **Xcode Command Line Tools** (Homebrew needs them):

   ```bash
   xcode-select --install
   ```

2. **Homebrew** — doctor _uses_ brew to install things, but it can't install brew itself:

   ```bash
   /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
   ```

   Follow the printed "Next steps" to add brew to your `PATH`.

3. **uv** — the `./schematic` launcher runs everything inside a uv-managed environment, so uv needs
   to be there before your first `./schematic` call:

   ```bash
   brew install uv
   ```

4. **A copy of Satisfactory** matching the pinned version above. Doctor _verifies_ the version and
   stops if it doesn't match, but it can't download or update the game for you (see
   [Getting the game](#getting-the-game)).

   Good news: you usually don't need to configure the path. Doctor scans the common install spots
   (macOS / Windows / Linux Steam, Epic) and, when it finds one, caches it to
   `config/config.local.yaml` so every later run resolves it instantly. If you need to point it
   somewhere specific, set `game.path` in `config/config.local.yaml`.

## Run the doctor

```bash
./schematic doctor          # report only
./schematic doctor --fix    # run the safe fixes (downloads + brew installs) after confirming
```

From here doctor takes over. With your OK, it can install or fetch:

- Docker Desktop (`brew install --cask docker`)
- Blender (`brew install --cask blender`)
- `potrace` and `rsvg-convert`
- the Oodle + zlib libraries (into `build/00-doctor/libs/`)
- the pre-commit git hooks
- the .NET SDK (optional — only if you're working on the native extractor)

## Getting the game

Doctor checks for the game but never downloads it. A couple of ways to get there:

- **Already own it on Steam (any OS)?** Just point doctor at that install directory.
- **On macOS with no local install?** Satisfactory is Windows-only, but SteamCMD can grab the
  Windows depot — the files don't need to _run_, we only read the paks + `CommunityResources`. You
  do need to own the game on the account you log in with (~40 GB, interactive Steam Guard):

  ```bash
  brew install steamcmd
  steamcmd +@sSteamCmdForcePlatformType windows \
           +force_install_dir "$PWD/game" \
           +login <steam-username> \
           +app_update 526870 validate +quit
  ```

If your installed version doesn't match `config/config.yaml`, doctor stops with a clear message.
Either install the matching build, or bump `game.version` / `game.engineVersion` in
`config/config.yaml` **and re-check the CUE4Parse settings** (a wrong engine version is likely to mangle meshes when trying to read).

## Things you finish by hand

A few things doctor will flag but leave for you:

- **Start the Docker daemon.** Doctor can install Docker Desktop, but you have to launch it
  (`open -a Docker`) and wait for it to be ready before extracting.
- **Blender version drift.** Doctor warns if the Blender it found isn't the expected major.minor
  (Freestyle behaves differently across versions); grabbing an exact older build can be manual.

## How the pipeline works

The whole thing is two commands under the hood:

**Extract**

- Builds a Docker image with a patched CUE4Parse + Oodle.
- Mounts your local game folder and this repo.
- Pulls meshes (`.glb`) and game data (`.json`) into a local cache.

**Build**

- Runs a Blender script to produce line/area info and interstitial PNGs.
- Reads the game data for ports, orientation, and collision boxes.
- Renders lines, areas, ports, and collision info (with your theme applied) into SVGs.
- Re-renders those final SVGs as PNGs.
- Produces the preview HTML and the final ZIP in `dist/`.
