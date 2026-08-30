// The four prebaked themes, in dropdown order. Names + blurbs mirror the README so the site and the
// repo stay in sync. `slug` is the folder name under public/themes/<slug>/ and the release-asset
// prefix (<slug>-<version>.zip).

export interface ThemeInfo {
  slug: string;
  name: string;
  blurb: string;
}

export const THEMES: ThemeInfo[] = [
  {
    slug: "blue-schematic",
    name: "Blue Schematic",
    blurb: "Crisp architect-blue line art with port + collision annotations.",
  },
  {
    slug: "blue-schematic-clean",
    name: "Blue Schematic (Clean)",
    blurb: "Same clean blue lines, no port or collision annotations.",
  },
  {
    slug: "blue-excalidraw",
    name: "Blue Excalidraw",
    blurb: "Thicker, hand-drawn wobble for that sketched Excalidraw look.",
  },
  {
    slug: "blue-excalidraw-clean",
    name: "Blue Excalidraw (Clean)",
    blurb: "Hand-drawn look, no port or collision annotations.",
  },
];

export const DEFAULT_THEME = "blue-schematic";

export function themeBySlug(slug: string): ThemeInfo | undefined {
  return THEMES.find((t) => t.slug === slug);
}
