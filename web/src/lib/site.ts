// Site-wide constants. Repo coordinates + the current release version all come from release.json,
// the one file you edit when you cut a new version. The download modal, the footer links, and the
// CI `fetch-dist` script (which rebuilds dist/ from the published release) all read the same source.
import release from "../../release.json";

export const REPO_OWNER = release.owner;
export const REPO_NAME = release.repo;
export const REPO_URL = `https://github.com/${REPO_OWNER}/${REPO_NAME}`;
export const RELEASES_URL = `${REPO_URL}/releases`;
export const LATEST_RELEASE_URL = `${RELEASES_URL}/latest`;

// The release the download page points at. Bump the "version" in release.json after you upload a new
// one (`./schematic upload --all-themes --version x.y.z`). Download links are built as
// .../releases/download/v<VERSION>/<slug>-<VERSION>.zip, matching how upload names its assets.
export const CURRENT_VERSION = release.version;
export const CURRENT_TAG = `v${CURRENT_VERSION}`;

/** Direct download URL for a theme's zip on the current release. */
export function zipUrl(slug: string): string {
  return `${RELEASES_URL}/download/${CURRENT_TAG}/${slug}-${CURRENT_VERSION}.zip`;
}

export const TAGLINE =
  "Pre-rendered images of Satisfactory buildings, for use in your favorite diagramming tools.";
