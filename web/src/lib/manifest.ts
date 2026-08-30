// Typed access to the pipeline manifest (preview.json / metadata.json, schema "satisfactory.preview/1").
//
// The structure (categories, builds, views, dimensions) is theme-independent -- every theme ships
// the identical filenames -- so we read ONE synced manifest at build time and drive the whole
// gallery from it. Per-theme image URLs are just a path-prefix swap at runtime (see the theme island).

import raw from "../data/preview.json";

export interface Dim3 {
  x: number;
  y: number;
  z: number;
}

export interface ManifestView {
  view: string;
  svg: string; // e.g. "svg/constructor_top.svg"
  png: string | null;
  width_px: number | null;
  height_px: number | null;
  width_m: number | null;
  height_m: number | null;
}

export interface ManifestBuild {
  label: string;
  category: string;
  source: string | null;
  ppm: number | null;
  grid_m: number | null;
  bbox_m: Dim3 | null;
  clearance_m: unknown;
  views: ManifestView[];
}

export interface ManifestCategory {
  id: string;
  name: string;
  blurb: string;
  builds: string[]; // stems, in display order
}

export interface Manifest {
  schema: string;
  counts: { categories: number; buildings: number; views: number };
  categories: ManifestCategory[];
  buildings: Record<string, ManifestBuild>;
}

export const manifest = raw as unknown as Manifest;

export const categories = manifest.categories;
export const buildings = manifest.buildings;
export const counts = manifest.counts;

/** Just the filename (drops the leading "svg/"), which is identical across every theme. */
export function svgFile(view: ManifestView): string {
  return view.svg.replace(/^svg\//, "");
}
