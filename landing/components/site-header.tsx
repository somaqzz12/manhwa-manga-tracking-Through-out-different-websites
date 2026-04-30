"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { dashboardUrl, githubUrl, webStoreUrl } from "@/lib/site-config";

export function SiteHeader() {
  const [isDark, setIsDark] = useState(false);
  const base = dashboardUrl.replace(/\/$/, "");

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
    <header className="sticky top-0 z-50 border-b border-[color-mix(in_srgb,var(--color-border)_25%,transparent)] bg-[color-mix(in_srgb,var(--color-surface)_82%,transparent)] backdrop-blur-[14px] dark:bg-[color-mix(in_srgb,var(--color-surface)_55%,transparent)]">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-4 py-3 sm:px-6">
        <Link href="/" className="flex items-center gap-2 font-semibold text-[var(--color-text)]">
          <span
            className="grid size-9 place-items-center rounded-xl bg-gradient-to-br from-[var(--color-accent-2)] to-[var(--color-accent)] text-sm font-bold text-[#fffaf3] shadow-accent"
            aria-hidden
          >
            MW
          </span>
          <span className="font-serif tracking-tight">Manga Watchlist</span>
        </Link>
        <nav className="flex flex-wrap items-center justify-end gap-x-4 gap-y-2 text-sm font-semibold" aria-label="Primary">
          <a href={`${base}/discover`} className="text-[var(--color-muted)] no-underline transition hover:text-[var(--color-text)]">
            Discover
          </a>
          <a href={`${base}/sources`} className="text-[var(--color-muted)] no-underline transition hover:text-[var(--color-text)]">
            Sources
          </a>
          <a
            href={`${base}/extension`}
            className="text-[var(--color-muted)] no-underline transition hover:text-[var(--color-text)]"
          >
            Extension
          </a>
          <a
            href={githubUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="text-[var(--color-muted)] no-underline transition hover:text-[var(--color-text)]"
          >
            GitHub
          </a>
          <a href={`${base}/auth?mode=login`} className="text-[var(--color-muted)] no-underline transition hover:text-[var(--color-text)]">
            Sign in
          </a>
          <a href={`${base}/auth?mode=register`} className="text-[var(--color-muted)] no-underline transition hover:text-[var(--color-text)]">
            Create account
          </a>
          <a
            href={`${base}/app`}
            className="rounded-full border border-[var(--color-border)] bg-[var(--color-surface-2)] px-3 py-1.5 text-[var(--color-text)] no-underline transition hover:border-[var(--color-accent)]"
          >
            Open app
          </a>
          {webStoreUrl.length > 0 ? (
            <Link
              href={webStoreUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="hidden rounded-full border border-[var(--color-border)] px-3 py-1.5 text-[var(--color-muted)] no-underline sm:inline hover:text-[var(--color-text)]"
            >
              Chrome
            </Link>
          ) : null}
          <button
            type="button"
            onClick={toggleTheme}
            className="btn-glass rounded-full px-3 py-1.5 text-sm text-[var(--color-text)]"
            aria-label="Toggle theme"
          >
            {isDark ? "☾" : "☀"}
          </button>
        </nav>
      </div>
    </header>
  );
}
