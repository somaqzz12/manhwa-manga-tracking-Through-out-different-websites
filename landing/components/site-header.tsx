"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ChromeIcon } from "@/components/chrome-icon";
import {
  extensionZipDownloadUrl,
  githubUrl,
  webStoreUrl,
} from "@/lib/site-config";

function ExtensionCtas() {
  const zip = (
    <a
      href={extensionZipDownloadUrl}
      target="_blank"
      rel="noopener noreferrer"
      className={
        webStoreUrl.length > 0
          ? "btn-glass inline-flex items-center gap-2 rounded-full px-3 py-2 text-sm font-semibold text-[var(--color-text)] outline-none transition duration-200 hover:-translate-y-0.5 focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]"
          : "btn-primary inline-flex items-center gap-2 rounded-full px-4 py-2.5 text-sm font-semibold text-white outline-none transition duration-200 hover:-translate-y-0.5 focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]"
      }
      aria-label="Download extension as ZIP"
    >
      {webStoreUrl.length === 0 ? (
        <ChromeIcon className="h-5 w-5 text-white" />
      ) : null}
      {webStoreUrl.length > 0 ? "ZIP" : "Download extension"}
    </a>
  );

  if (webStoreUrl.length > 0) {
    return (
      <>
        <Link
          href={webStoreUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="btn-primary inline-flex items-center gap-2 rounded-full px-4 py-2.5 text-sm font-semibold text-white outline-none transition duration-200 hover:-translate-y-0.5 focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]"
          aria-label="Add to Chrome"
        >
          <ChromeIcon className="h-5 w-5 text-white" />
          Add to Chrome
        </Link>
        {zip}
      </>
    );
  }

  return zip;
}

export function SiteHeader() {
  const [isDark, setIsDark] = useState(false);

  useEffect(() => {
    const saved = localStorage.getItem("theme");
    const dark = saved === "dark";
    document.documentElement.classList.toggle("dark", dark);
    setIsDark(dark);
  }, []);

  function toggleTheme() {
    const next = !isDark;
    document.documentElement.classList.toggle("dark", next);
    localStorage.setItem("theme", next ? "dark" : "light");
    setIsDark(next);
  }

  return (
    <header className="sticky top-0 z-50 border-b border-[color-mix(in_srgb,var(--color-border)_25%,transparent)] bg-[rgba(255,255,255,0.25)] backdrop-blur-[14px] dark:bg-[rgba(255,255,255,0.06)]">
      <div className="mx-auto flex h-14 max-w-6xl items-center justify-between px-4 sm:px-6">
        <Link href="/" className="flex items-center gap-2 font-semibold text-[var(--color-text)]">
          <span
            className="grid size-9 place-items-center rounded-xl bg-gradient-to-br from-[var(--color-accent)] to-[#9a80ff] text-sm font-bold text-white shadow-accent"
            aria-hidden
          >
            MW
          </span>
          <span className="font-serif tracking-tight">Manga Watchlist</span>
        </Link>
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={toggleTheme}
            className="btn-glass rounded-full px-4 py-2 text-sm text-[var(--color-text)] transition duration-200 hover:-translate-y-0.5"
            aria-label="Toggle theme"
          >
            {isDark ? "☾" : "☀"}
          </button>
          <Link
            href={githubUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="hidden text-sm font-medium text-[var(--color-muted)] transition hover:text-[var(--color-text)] sm:inline"
          >
            GitHub
          </Link>
          <ExtensionCtas />
        </div>
      </div>
    </header>
  );
}
