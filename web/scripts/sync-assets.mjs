// Copy the pipeline's finished output into the site.
//
// The `./schematic build --all-themes` step writes dist/<slug>/{svg,png,metadata.json,...}. The
// site only needs the SVGs + each theme's manifest (PNGs stay in the downloadable zip). We mirror
// those into public/themes/<slug>/, drop the hero art into public/docs/, and stash one manifest at
// src/data/preview.json so the gallery can read its (theme-independent) structure at build time.
//
// Run automatically by `npm run dev` / `npm run build`. Safe to re-run; it clears what it owns.

import { cp, mkdir, readdir, readFile, rm, stat, writeFile } from "node:fs/promises";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const WEB = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const REPO = resolve(WEB, "..");
const DIST = join(REPO, "dist");
const DOCS = join(REPO, "docs");
const OUT_THEMES = join(WEB, "public", "themes");
const OUT_DOCS = join(WEB, "public", "docs");
const OUT_DATA = join(WEB, "src", "data", "preview.json");

// Which manifest seeds the (theme-independent) gallery structure. Every theme ships the same
// filenames, so any of them works; this is just the default we read at build time.
const STRUCTURE_THEME = "blue-schematic";

// Hero / social art lifted from the repo docs folder.
const DOC_IMAGES = ["blender_back.png", "excalidraw_foundries_ports.png", "drawio_assembler_ticks.png"];

async function exists(p) {
  try {
    await stat(p);
    return true;
  } catch {
    return false;
  }
}

async function themeSlugs() {
  if (!(await exists(DIST))) return [];
  const entries = await readdir(DIST, { withFileTypes: true });
  const slugs = [];
  for (const e of entries) {
    if (e.isDirectory() && (await exists(join(DIST, e.name, "metadata.json")))) {
      slugs.push(e.name);
    }
  }
  return slugs.sort();
}

async function main() {
  const slugs = await themeSlugs();
  if (slugs.length === 0) {
    console.error(
      `[sync] no themes found in ${DIST}.\n` +
        `[sync] run \`./schematic build --all-themes\` in the repo root first.`,
    );
    process.exit(1);
  }

  await rm(OUT_THEMES, { recursive: true, force: true });
  await mkdir(OUT_THEMES, { recursive: true });

  for (const slug of slugs) {
    const src = join(DIST, slug);
    const dest = join(OUT_THEMES, slug);
    await mkdir(dest, { recursive: true });
    await cp(join(src, "svg"), join(dest, "svg"), { recursive: true });
    await cp(join(src, "metadata.json"), join(dest, "metadata.json"));
  }

  // Seed the build-time structure manifest (fall back to the first theme if the default is absent).
  const structureSlug = slugs.includes(STRUCTURE_THEME) ? STRUCTURE_THEME : slugs[0];
  await mkdir(dirname(OUT_DATA), { recursive: true });
  await cp(join(DIST, structureSlug, "metadata.json"), OUT_DATA);

  // Hero / social imagery.
  await mkdir(OUT_DOCS, { recursive: true });
  for (const img of DOC_IMAGES) {
    const from = join(DOCS, img);
    if (await exists(from)) await cp(from, join(OUT_DOCS, img));
  }

  const manifest = JSON.parse(await readFile(OUT_DATA, "utf8"));
  const svgCount = Object.values(manifest.buildings).reduce((n, b) => n + b.views.length, 0);
  await writeFile(
    join(OUT_THEMES, "index.json"),
    JSON.stringify({ themes: slugs, structure: structureSlug }, null, 2) + "\n",
  );
  console.log(
    `[sync] ${slugs.length} theme(s): ${slugs.join(", ")}  ` +
      `(${manifest.counts.buildings} builds, ${svgCount} views each)`,
  );
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
