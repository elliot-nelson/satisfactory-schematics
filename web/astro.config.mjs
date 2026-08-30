// @ts-check
import { defineConfig } from "astro/config";
import tailwindcss from "@tailwindcss/vite";

// Static marketing + preview site. `site` gets set for real once a domain is picked; for now
// the defaults are fine for `astro dev` / `astro build` locally.
export default defineConfig({
  vite: {
    plugins: [tailwindcss()],
  },
});
