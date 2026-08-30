// Site-wide constants. Keep repo coordinates in one place so the GitHub corner, download modal, and
// release fetch all agree.

export const REPO_OWNER = "elliot-nelson";
export const REPO_NAME = "satisfactory-schematics";
export const REPO_URL = `https://github.com/${REPO_OWNER}/${REPO_NAME}`;
export const RELEASES_URL = `${REPO_URL}/releases`;
export const LATEST_RELEASE_URL = `${RELEASES_URL}/latest`;

// ---------------------------------------------------------------------------
// Current release the download page points at. Bump this when you cut + upload a
// new version (`./schematic upload --all-themes --version x.y.z`). The download
// links are built as .../releases/download/v<VERSION>/<slug>-<VERSION>.zip, which
// matches how the upload command names its assets.
// ---------------------------------------------------------------------------
export const CURRENT_VERSION = "0.1.0";
export const CURRENT_TAG = `v${CURRENT_VERSION}`;

/** Direct download URL for a theme's zip on the current release. */
export function zipUrl(slug: string): string {
  return `${RELEASES_URL}/download/${CURRENT_TAG}/${slug}-${CURRENT_VERSION}.zip`;
}

export const TAGLINE =
  "Pre-rendered images of Satisfactory buildings, for use in your favorite diagramming tools.";
