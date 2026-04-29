"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ChromeIcon } from "@/components/chrome-icon";
import { githubUrl, webStoreUrl } from "@/lib/site-config";

function primaryCta() {
  const label =
    webStoreUrl.length > 0 ? "Add to Chrome" : "Extension source";
  const href =
    webStoreUrl.length > 0
      ? webStoreUrl
      : `${githubUrl}/tree/main/extension`;
  const external = true;
  return (
    <Link
      href={href}
      className="inline-flex items-center gap-2 rounded-full bg-gradient-to-br from-[var(--color-accent)] to-[#9a80ff] px-4 py-2 text-sm font-semibold text-white shadow-accent outline-none ring-1 ring-white/15 transition hover:brightness-105 focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]"
      {...(external ? { target: "_blank", rel: "noopener noreferrer" } : {})}
      aria-label={label}
    >
      <ChromeIcon className="h-5 w-5 text-white" />
      {label}
    </Link>
  );
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
    <header className="sticky top-0 z-50 border-b border-[var(--color-border)] bg-background/85 backdrop-blur-md">
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
            className="rounded-full border border-[var(--color-border)] px-3 py-1.5 text-sm text-[var(--color-text)] transition hover:translate-y-[-1px]"
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
          {primaryCta()}
        </div>
      </div>
    </header>
  );
}
