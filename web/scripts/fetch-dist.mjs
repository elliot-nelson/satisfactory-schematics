// Recreate the repo's dist/ folder from a published GitHub Release.
//
// Why: the site needs the rendered theme assets in ../dist/<slug>/, but the machine building the
// site (Netlify, GitHub Actions, ...) can't run Blender. So instead of rendering, we just download
// what we already published. This script reads web/release.json for the repo + version, fetches the
// matching release, and unzips every attached <slug>-<version>.zip into ../dist/<slug>/ -- leaving
// dist/ looking exactly as if it had been built locally. Then `npm run build` (sync + astro) works.
//
// Usage (from web/):  npm run fetch-dist      (or `npm run build:netlify` to fetch + build in one go)
//
// Our releases page is public, so no credentials are needed -- this happily runs on Netlify's build
// box. If GITHUB_TOKEN happens to be set (e.g. inside Actions) we send it on the API call to dodge
// the anonymous rate limit; asset downloads always use the public browser_download_url.

import { spawnSync } from "node:child_process";
import { mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const WEB = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const REPO_ROOT = resolve(WEB, "..");
const DIST = join(REPO_ROOT, "dist");
const CONFIG = join(WEB, "release.json");

function die(msg) {
  console.error(`[fetch-dist] ${msg}`);
  process.exit(1);
}

async function main() {
  // We shell out to `unzip` -- preinstalled on GitHub + Netlify Linux images and on macOS.
  if (spawnSync("unzip", ["-v"], { stdio: "ignore" }).status !== 0) {
    die("`unzip` not found on PATH. Install it (it ships on GitHub + Netlify build images).");
  }

  const cfg = JSON.parse(await readFile(CONFIG, "utf8"));
  const { owner, repo, version } = cfg;
  if (!owner || !repo || !version) {
    die(`release.json needs { owner, repo, version }. Got: ${JSON.stringify(cfg)}`);
  }
  const tag = `v${version}`;

  const headers = {
    Accept: "application/vnd.github+json",
    "User-Agent": `${repo}-web`,
    "X-GitHub-Api-Version": "2022-11-28",
  };
  if (process.env.GITHUB_TOKEN) headers.Authorization = `Bearer ${process.env.GITHUB_TOKEN}`;

  const api = `https://api.github.com/repos/${owner}/${repo}/releases/tags/${tag}`;
  console.log(`[fetch-dist] GET ${owner}/${repo} release ${tag}`);
  const res = await fetch(api, { headers });
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    const hint = res.status === 404 ? "no release published for that tag yet." : body.slice(0, 300);
    die(`GitHub API returned ${res.status} for ${tag} -- ${hint}`);
  }
  const release = await res.json();

  const suffix = `-${version}.zip`;
  const zips = (release.assets ?? []).filter((a) => a.name.endsWith(suffix));
  if (zips.length === 0) die(`release ${tag} has no *${suffix} assets attached.`);

  await rm(DIST, { recursive: true, force: true });
  await mkdir(DIST, { recursive: true });
  const tmp = await mkdtemp(join(tmpdir(), "sat-dist-"));

  for (const asset of zips) {
    const slug = asset.name.slice(0, -suffix.length);
    const dest = join(DIST, slug);
    const zipPath = join(tmp, asset.name);
    process.stdout.write(`[fetch-dist] ${asset.name} -> dist/${slug}/ ... `);

    const dl = await fetch(asset.browser_download_url, {
      headers: { "User-Agent": headers["User-Agent"] },
    });
    if (!dl.ok) die(`\n  download failed (${dl.status}) for ${asset.browser_download_url}`);
    await writeFile(zipPath, Buffer.from(await dl.arrayBuffer()));

    await mkdir(dest, { recursive: true });
    const un = spawnSync("unzip", ["-o", "-q", zipPath, "-d", dest], { stdio: "inherit" });
    if (un.status !== 0) die(`\n  unzip failed for ${asset.name}`);
    console.log("ok");
  }

  await rm(tmp, { recursive: true, force: true });
  const slugs = zips.map((z) => z.name.slice(0, -suffix.length));
  console.log(`[fetch-dist] recreated dist/ with ${slugs.length} theme(s): ${slugs.join(", ")}`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
