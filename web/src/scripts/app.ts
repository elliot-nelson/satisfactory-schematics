// All the site's interactivity in one tiny island: theme switching, the zoom lightbox, and the
// download shutterbox. No framework -- just DOM.

import { DEFAULT_THEME, themeBySlug } from "../lib/themes";
import { CURRENT_VERSION, zipUrl } from "../lib/site";

const STORAGE_KEY = "sf-theme";

/* ---------------------------------------------------------------- theme swap */

function applyTheme(slug: string): void {
  const info = themeBySlug(slug);
  if (!info) return;
  document.documentElement.dataset.theme = slug;

  for (const img of document.querySelectorAll<HTMLImageElement>("img[data-file]")) {
    img.src = `/themes/${slug}/svg/${img.dataset.file}`;
  }
  for (const blurb of document.querySelectorAll<HTMLElement>("[data-theme-blurb]")) {
    blurb.textContent = info.blurb;
  }
  for (const sel of document.querySelectorAll<HTMLSelectElement>("select.js-theme-select")) {
    if (sel.value !== slug) sel.value = slug;
  }
  for (const link of document.querySelectorAll<HTMLAnchorElement>("[data-download-zip]")) {
    link.href = zipUrl(slug);
    const name = link.querySelector<HTMLElement>("[data-zip-name]");
    if (name) name.textContent = `${slug}-${CURRENT_VERSION}.zip`;
  }
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
  for (const sel of document.querySelectorAll<HTMLSelectElement>("select.js-theme-select")) {
    sel.addEventListener("change", () => applyTheme(sel.value));
  }
  applyTheme(saved && themeBySlug(saved) ? saved : DEFAULT_THEME);
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
