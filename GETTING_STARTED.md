# Getting Started

This covers the handful of steps **`sat doctor` cannot do for you** — the bootstrap. Once
these are in place, run `./sat doctor` and it takes over the rest (checking, downloading, and
installing everything else, with confirmation).

> **Maintenance rule:** this file documents *only* what doctor can't cover. Whenever we add a
> new manual prerequisite (or move one into doctor's automation), update this file in the same
> change. If doctor can install it, it belongs in doctor — not here.

Platform: **macOS on Apple Silicon** (the current support target).

---

## 1. Bootstrap (do these once, in order)

Doctor is itself a Python program launched through `uv`, so a few things must exist before it
can run at all:

1. **Xcode Command Line Tools** (Homebrew needs them):

   ```bash
   xcode-select --install
   ```

2. **Homebrew** — doctor *uses* brew to install things, but can't install brew itself:

   ```bash
   /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
   ```

   Follow the printed "Next steps" to add brew to your `PATH`.

3. **uv** — the `./sat` launcher runs everything inside a uv-managed environment, so uv must
   be present before the first `./sat` call:

   ```bash
   brew install uv
   ```

4. **A Satisfactory install** that matches the pinned version in
   [`config.yaml`](config.yaml) — currently **game `1.2.4.0`, engine UE `5.6.1`**. Doctor
   **verifies** the version and hard-stops on a mismatch, but it can't obtain or update the
   game for you. See [§3](#3-getting-the-game) below. Point doctor at it via either:
   - `game.path` in `config.yaml`, or
   - `export SAT_GAME_DIR=/path/to/Satisfactory`, or
   - drop/symlink it at `./game` (or `../game`), which doctor auto-detects.

---

## 2. Run the doctor

```bash
./sat doctor          # report only
./sat doctor --fix    # run the safe remediations (downloads + brew installs) after confirming
```

From here doctor handles the rest. **It can install / fetch for you** (with confirmation):

- Docker Desktop (`brew install --cask docker`)
- Blender (`brew install --cask blender`)
- `potrace` and `rsvg-convert`
- the Oodle + zlib libraries (downloaded into `build/00-doctor/libs/`)
- the pre-commit git hooks
- the .NET SDK (optional; only for native extractor development)

---

## 3. Getting the game

Doctor checks the game but never downloads it. Options:

- **You already own it on Steam (any OS):** point doctor at that install directory.
- **macOS, no local install:** Satisfactory is Windows-only, but SteamCMD can fetch the
  Windows depot (the files don't need to *run* — we only read the paks + `CommunityResources`).
  You must own the game on the Steam account you log in with (~40 GB, interactive Steam Guard):

  ```bash
  brew install steamcmd
  steamcmd +@sSteamCmdForcePlatformType windows \
           +force_install_dir "$PWD/game" \
           +login <steam-username> \
           +app_update 526870 validate +quit
  ```

  (A `./sat download` helper is planned; for now this is manual.)

If your installed version differs from `config.yaml`, doctor stops with a clear message. Either
install the matching game build, or bump `game.version` / `game.engineVersion` in `config.yaml`
**and re-validate the CUE4Parse settings** (see `../SPEC.md` §12.1) — a wrong engine version
silently misreads mesh bytes.

---

## 4. Things doctor flags but you finish by hand

- **Start the Docker daemon.** Doctor can install Docker Desktop, but you must launch it
  (`open -a Docker`) and wait until it's ready before extraction.
- **Blender version drift.** Doctor warns if the found Blender isn't the expected major.minor
  (Freestyle behaviors are version-sensitive); installing an exact older build can be manual.
- **First run is slow.** Building the extractor Docker image and (on macOS) the SteamCMD
  download take real time. Expected, one-time.
