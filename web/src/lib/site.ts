// Site-wide constants. Keep repo coordinates in one place so the GitHub corner, download modal, and
// release fetch all agree.

export const REPO_OWNER = "elliot-nelson";
export const REPO_NAME = "satisfactory-schematics";
export const REPO_URL = `https://github.com/${REPO_OWNER}/${REPO_NAME}`;
export const RELEASES_URL = `${REPO_URL}/releases`;
export const LATEST_RELEASE_URL = `${RELEASES_URL}/latest`;
export const RELEASES_API = `https://api.github.com/repos/${REPO_OWNER}/${REPO_NAME}/releases/latest`;

export const TAGLINE =
  "Pre-rendered images of Satisfactory buildings, for use in your favorite diagramming tools.";
