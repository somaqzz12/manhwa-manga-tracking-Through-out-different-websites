"use client";

import { FormEvent } from "react";
import { dashboardUrl } from "@/lib/site-config";

export function Hero() {
  const base = dashboardUrl.replace(/\/$/, "");
  const discover = `${base}/discover`;

  function onSubmit(e: FormEvent<HTMLFormElement>) {
    const fd = new FormData(e.currentTarget);
    const raw = String(fd.get("q") || "").trim();
    if (/^https?:\/\//i.test(raw)) {
      e.preventDefault();
      window.location.href = `${discover}?url=${encodeURIComponent(raw)}`;
    }
  }

  return (
    <section className="section px-4 pb-16 pt-12 sm:px-8 md:px-12 max-w-6xl mx-auto">
      <h1 className="font-serif text-[clamp(1.9rem,6vw,3rem)] leading-[1.08] mb-5 text-[var(--color-text)] tracking-tight max-w-4xl">
        Discover manga and manhwa. Track updates everywhere.
      </h1>
      <p className="text-lg text-[var(--color-muted)] mb-8 max-w-2xl leading-relaxed">
        Search a title or paste a URL. Manga Watchlist finds covers, descriptions, chapters, available websites,
        and the best source to track.
      </p>

      <div className="rounded-3xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6 md:p-8 shadow-sm mb-8">
        <form action={discover} method="get" className="flex flex-col gap-3 sm:flex-row sm:items-stretch" onSubmit={onSubmit}>
          <input
            name="q"
            type="search"
            placeholder="Search manga, manhwa, or paste a URL…"
            className="flex-1 min-w-0 rounded-full border border-[var(--color-border)] bg-[var(--color-surface-2)] px-5 py-3.5 text-[var(--color-text)] placeholder:text-[var(--color-muted)] outline-none focus:ring-2 focus:ring-[color-mix(in_srgb,var(--color-accent)_45%,transparent)]"
            aria-label="Search or paste URL"
            autoComplete="off"
          />
          <button
            type="submit"
            className="btn-primary shrink-0 rounded-full px-8 py-3.5 text-sm font-semibold transition duration-200 hover:-translate-y-0.5"
          >
            Search
          </button>
        </form>
        <div className="mt-4 flex flex-wrap gap-3">
          <a
            href={`${base}/app/add`}
            className="btn-primary inline-flex items-center justify-center rounded-full px-6 py-3 text-sm font-semibold no-underline transition duration-200 hover:-translate-y-0.5"
          >
            Add URL
          </a>
          <a
            href={discover}
            className="btn-glass inline-flex items-center justify-center rounded-full px-6 py-3 text-sm font-semibold text-[var(--color-text)] no-underline transition duration-200 hover:-translate-y-0.5"
          >
            Browse discover
          </a>
        </div>
      </div>

      <p className="text-sm text-[var(--color-muted)]">
        Try:{" "}
        <a href={`${discover}?q=Solo+Leveling`} className="font-semibold text-[var(--color-accent)] no-underline hover:underline">
          Solo Leveling
        </a>
        {" · "}
        <a href={`${discover}?q=One+Piece`} className="font-semibold text-[var(--color-accent)] no-underline hover:underline">
          One Piece
        </a>
        {" · "}
        <a href={`${discover}?q=Tower+of+God`} className="font-semibold text-[var(--color-accent)] no-underline hover:underline">
          Tower of God
        </a>
        {" · "}
        <a
          href={`${discover}?q=Omniscient+Reader`}
          className="font-semibold text-[var(--color-accent)] no-underline hover:underline"
        >
          Omniscient Reader
        </a>
      </p>

      <p className="mt-8 max-w-lg text-sm leading-relaxed text-[var(--color-muted)]">
        Optional browser companion:{" "}
        <a
          href={`${base}/extension`}
          className="font-semibold text-[var(--color-accent)] no-underline hover:underline"
        >
          Get extension
        </a>{" "}
        — add pages from sites you already use. Install and privacy details are on that page.
      </p>
    </section>
  );
}
