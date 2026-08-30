// All the site's interactivity in one tiny island: theme switching, the zoom lightbox, and the
// download shutterbox (incl. resolving the latest GitHub release). No framework -- just DOM.

import { THEMES, DEFAULT_THEME } from "../lib/themes";
import { RELEASES_API, LATEST_RELEASE_URL } from "../lib/site";

const STORAGE_KEY = "sf-theme";
const blurbBySlug = new Map(THEMES.map((t) => [t.slug, t.blurb]));

/* ---------------------------------------------------------------- theme swap */

function applyTheme(slug: string): void {
  if (!blurbBySlug.has(slug)) return;
  document.documentElement.dataset.theme = slug;
  for (const img of document.querySelectorAll<HTMLImageElement>("img[data-file]")) {
    img.src = `/themes/${slug}/svg/${img.dataset.file}`;
  }
  const blurb = document.getElementById("theme-blurb");
  if (blurb) blurb.textContent = blurbBySlug.get(slug) ?? "";
  const sel = document.getElementById("theme-select") as HTMLSelectElement | null;
  if (sel && sel.value !== slug) sel.value = slug;
  // keep an open lightbox in sync
  const lbImg = document.getElementById("lightbox-img") as HTMLImageElement | null;
  if (lbImg?.dataset.file) lbImg.src = `/themes/${slug}/svg/${lbImg.dataset.file}`;
  try {
    localStorage.setItem(STORAGE_KEY, slug);
  } catch {
    /* private mode: ignore */
  }
}

function initTheme(): void {
  let saved: string | null = null;
  try {
    saved = localStorage.getItem(STORAGE_KEY);
  } catch {
    /* ignore */
  }
  const sel = document.getElementById("theme-select") as HTMLSelectElement | null;
  sel?.addEventListener("change", () => applyTheme(sel.value));
  if (saved && saved !== DEFAULT_THEME) applyTheme(saved);
  else document.documentElement.dataset.theme = DEFAULT_THEME;
}

/* ------------------------------------------------------------------ lightbox */

function openLightbox(img: HTMLImageElement): void {
  const lb = document.getElementById("lightbox");
  const lbImg = document.getElementById("lightbox-img") as HTMLImageElement | null;
  const cap = document.getElementById("lightbox-cap");
  if (!lb || !lbImg) return;
  lbImg.src = img.src;
  lbImg.dataset.file = img.dataset.file ?? "";
  lbImg.alt = img.alt;
  if (cap) cap.textContent = img.alt;
  showOverlay(lb);
}

/* ------------------------------------------------------------- download modal */

interface ReleaseAsset {
  name: string;
  browser_download_url: string;
  size: number;
}
interface Release {
  tag_name: string;
  assets: ReleaseAsset[];
}

let releaseLoaded = false;

function humanSize(bytes: number): string {
  if (bytes >= 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  return `${Math.round(bytes / 1024)} KB`;
}

function escapeRe(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

async function loadRelease(): Promise<void> {
  if (releaseLoaded) return;
  releaseLoaded = true;

  const sub = document.getElementById("dl-release");
  let release: Release | null = null;
  try {
    const cached = sessionStorage.getItem("sf-release");
    if (cached) release = JSON.parse(cached);
  } catch {
    /* ignore */
  }

  if (!release) {
    try {
      const res = await fetch(RELEASES_API, { headers: { Accept: "application/vnd.github+json" } });
      if (res.ok) {
        release = (await res.json()) as Release;
        try {
          sessionStorage.setItem("sf-release", JSON.stringify(release));
        } catch {
          /* ignore */
        }
      }
    } catch {
      /* offline / rate-limited -> fall through to fallback links */
    }
  }

  if (!release) {
    if (sub) {
      sub.innerHTML = `No release fetched &mdash; <a href="${LATEST_RELEASE_URL}" target="_blank" rel="noopener" style="color:var(--color-ficsit)">open the releases page &rarr;</a>`;
    }
    return;
  }

  if (sub) sub.textContent = `Latest release: ${release.tag_name}`;

  for (const link of document.querySelectorAll<HTMLAnchorElement>("[data-theme-zip]")) {
    const slug = link.dataset.themeZip!;
    const asset = release.assets.find(
      (a) => new RegExp(`^${escapeRe(slug)}-\\d`).test(a.name) && a.name.endsWith(".zip"),
    );
    const sizeEl = link.querySelector<HTMLElement>("[data-size]");
    if (asset) {
      link.href = asset.browser_download_url;
      if (sizeEl) sizeEl.textContent = humanSize(asset.size);
    } else if (sizeEl) {
      sizeEl.textContent = "ZIP";
    }
  }
}

/* -------------------------------------------------------------- overlay utils */

let lastFocus: HTMLElement | null = null;

function showOverlay(el: HTMLElement): void {
  lastFocus = document.activeElement as HTMLElement;
  el.hidden = false;
  el.setAttribute("aria-hidden", "false");
  document.body.style.overflow = "hidden";
}

function hideOverlay(el: HTMLElement): void {
  el.hidden = true;
  el.setAttribute("aria-hidden", "true");
  if (!document.querySelector(".lightbox:not([hidden]), .shutter:not([hidden])")) {
    document.body.style.overflow = "";
  }
  lastFocus?.focus?.();
}

function initOverlays(): void {
  const modal = document.getElementById("download-modal");

  document.addEventListener("click", (e) => {
    const target = e.target as HTMLElement;

    const dl = target.closest("[data-download]");
    if (dl && modal) {
      e.preventDefault();
      showOverlay(modal);
      void loadRelease();
      return;
    }

    const stage = target.closest(".stage");
    if (stage) {
      const img = stage.querySelector<HTMLImageElement>("img[data-file]");
      if (img) openLightbox(img);
      return;
    }

    const close = target.closest("[data-close]");
    if (close) {
      const overlay = close.closest<HTMLElement>(".shutter, .lightbox");
      if (overlay) hideOverlay(overlay);
    }
  });

  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    for (const el of document.querySelectorAll<HTMLElement>(
      ".lightbox:not([hidden]), .shutter:not([hidden])",
    )) {
      hideOverlay(el);
    }
  });
}

/* ----------------------------------------------------------------------- boot */

function boot(): void {
  initTheme();
  initOverlays();
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", boot);
} else {
  boot();
}
