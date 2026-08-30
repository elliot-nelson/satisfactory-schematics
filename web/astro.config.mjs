// @ts-check
import { defineConfig } from "astro/config";
import tailwindcss from "@tailwindcss/vite";

// Static marketing + preview site. `site` is the public origin -- it makes Astro.site available so
// we can emit absolute canonical + social (og/twitter) URLs, which scrapers require. Update this if
// the domain changes.
export default defineConfig({
  site: "https://satisfactory-schematics.7tonshark.com",
  vite: {
    plugins: [tailwindcss()],
  },
});
