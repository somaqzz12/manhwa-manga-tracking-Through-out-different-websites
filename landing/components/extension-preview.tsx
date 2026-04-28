"use client";

import Link from "next/link";
import { useState } from "react";
import { webStoreUrl } from "@/lib/site-config";

type TabId = "popup" | "dashboard" | "series";

const tabs: { id: TabId; label: string }[] = [
  { id: "popup", label: "Extension popup" },
  { id: "dashboard", label: "Library" },
  { id: "series", label: "Series cards" },
];

export function ExtensionPreview() {
  const [tab, setTab] = useState<TabId>("popup");

  return (
    <section className="border-t border-white/[0.06] px-4 py-20 sm:px-6">
      <div className="mx-auto max-w-6xl">
        <div className="mx-auto max-w-2xl text-center">
          <h2 className="text-3xl font-bold tracking-tight text-white sm:text-4xl">
            Extension preview
          </h2>
          <p className="mt-4 text-lg text-slate-400">
            Pop the tray for status and unread totals, then manage everything from
            the web dashboard — same bold dark UI end to end.
          </p>
        </div>

        <div className="mt-10 flex flex-wrap items-center justify-center gap-2">
          {tabs.map((t) => (
            <button
              key={t.id}
              type="button"
              onClick={() => setTab(t.id)}
              className={`rounded-full px-4 py-2 text-sm font-semibold transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400 ${
                tab === t.id
                  ? "bg-indigo-600 text-white shadow-accent"
                  : "border border-slate-600 bg-card text-slate-300 hover:border-indigo-500/40 hover:text-white"
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>

        <div className="relative mx-auto mt-10 max-w-4xl">
          <div className="pointer-events-none absolute -inset-4 rounded-[2rem] bg-gradient-to-tr from-indigo-500/15 via-transparent to-cyan-500/10 blur-2xl" />
          <div className="relative overflow-hidden rounded-2xl border border-slate-700/80 bg-[#070b14] shadow-accentLg ring-1 ring-white/[0.05]">
            <div className="aspect-[16/10] w-full">
              <PreviewMedia tab={tab} />
            </div>
          </div>
          <p className="mt-4 max-w-xl mx-auto text-center text-xs text-slate-500">
            Drop PNGs named{" "}
            <code className="rounded bg-white/[0.06] px-1 text-slate-400">
              extension-popup.png
            </code>
            ,{" "}
            <code className="rounded bg-white/[0.06] px-1 text-slate-400">
              dashboard.png
            </code>
            ,{" "}
            <code className="rounded bg-white/[0.06] px-1 text-slate-400">
              series-cards.png
            </code>{" "}
            into <code className="rounded bg-white/[0.06] px-1 text-slate-400">
              landing/public/screenshots/
            </code>
            {" — "}they load automatically; until then built-in mocks show layout.
          </p>
        </div>

        <div className="mt-8 flex flex-col items-center justify-center gap-3 sm:flex-row">
          {webStoreUrl.length > 0 ? (
            <Link
              href={webStoreUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="text-sm font-semibold text-indigo-300 underline-offset-4 transition hover:text-indigo-200 hover:underline"
            >
              View on Chrome Web Store →
            </Link>
          ) : (
            <span className="text-sm text-slate-500">
              Web Store link appears when{" "}
              <code className="text-slate-400">NEXT_PUBLIC_WEB_STORE_URL</code> is
              set.
            </span>
          )}
        </div>
      </div>
    </section>
  );
}

function PreviewMedia({ tab }: { tab: TabId }) {
  const map: Record<TabId, { src: string; alt: string }> = {
    popup: {
      src: "/screenshots/extension-popup.png",
      alt: "Manga Tracker browser extension popup showing connection status and unread count",
    },
    dashboard: {
      src: "/screenshots/dashboard.png",
      alt: "Manga Tracker web dashboard with search and statistics",
    },
    series: {
      src: "/screenshots/series-cards.png",
      alt: "Series cards with continue, edit, and chapter progress",
    },
  };
  const { src, alt } = map[tab];

  return (
    <div className="relative size-full min-h-[200px] bg-[#030712]">
      <ImageWithFallback src={src} alt={alt} tab={tab} />
    </div>
  );
}

function ImageWithFallback({
  src,
  alt,
  tab,
}: {
  src: string;
  alt: string;
  tab: TabId;
}) {
  const [ok, setOk] = useState(true);

  return (
    <div className="relative size-full min-h-[200px]">
      {!ok ? (
        <FallbackPreview tab={tab} />
      ) : (
        // Runtime-optional files in `public/screenshots/`; 404 swaps to mocks.
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={src}
          alt={alt}
          className="absolute inset-0 h-full min-h-[200px] w-full object-cover object-top"
          decoding="async"
          loading={tab === "popup" ? "eager" : "lazy"}
          onError={() => setOk(false)}
        />
      )}
    </div>
  );
}

function FallbackPreview({ tab }: { tab: TabId }) {
  if (tab === "popup") {
    return (
      <div className="flex size-full items-center justify-center p-6 sm:p-10">
        <div className="w-full max-w-xs rounded-2xl border border-slate-700 bg-[#0c1220] p-4 shadow-xl">
          <div className="mb-3 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="grid size-8 place-items-center rounded-lg bg-gradient-to-br from-indigo-400 to-indigo-600 text-xs font-bold text-white">
                MT
              </span>
              <span className="text-sm font-semibold text-white">Manga Tracker</span>
            </div>
            <span className="text-xs text-emerald-400">● Connected</span>
          </div>
          <div className="space-y-2">
            <div className="rounded-lg border border-slate-700/80 bg-slate-900/50 p-3">
              <p className="text-[10px] font-bold uppercase tracking-wider text-cyan-300/90">
                Unread chapters
              </p>
              <p className="text-2xl font-bold text-white">126</p>
            </div>
            <div className="rounded-lg border border-slate-700/80 bg-slate-900/50 p-3">
              <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500">
                No chapter detected
              </p>
              <p className="mt-1 text-xs text-slate-400">
                Open a chapter and reopen this popup to track it.
              </p>
            </div>
          </div>
          <div className="mt-3 grid grid-cols-2 gap-2">
            <span className="rounded-lg bg-slate-800 py-2 text-center text-xs font-medium text-slate-300">
              Open dashboard
            </span>
            <span className="rounded-lg bg-slate-800 py-2 text-center text-xs font-medium text-slate-300">
              Settings
            </span>
          </div>
        </div>
      </div>
    );
  }

  if (tab === "dashboard") {
    return (
      <div className="flex size-full flex-col gap-4 p-6 sm:p-8">
        <div className="flex flex-wrap gap-3">
          {["6 series", "126 behind", "5 up to date"].map((t) => (
            <div
              key={t}
              className="flex-1 min-w-[120px] rounded-xl border border-slate-700/80 bg-card px-4 py-3 text-center text-sm text-slate-300"
            >
              {t}
            </div>
          ))}
        </div>
        <div className="h-12 rounded-xl border border-dashed border-slate-600 bg-slate-900/40" />
        <div className="h-10 max-w-xs rounded-lg bg-indigo-600/80 text-center text-sm leading-10 text-white">
          Search library
        </div>
      </div>
    );
  }

  return (
    <div className="grid size-full gap-4 p-4 sm:grid-cols-3 sm:p-6">
      {[1, 2, 3].map((i) => (
        <div
          key={i}
          className="flex min-h-[140px] flex-row gap-3 overflow-hidden rounded-xl border border-slate-700/80 bg-card p-3"
        >
          <div className="aspect-[3/5] h-full min-h-[116px] w-20 shrink-0 rounded-lg bg-gradient-to-br from-slate-700 to-slate-900" />
          <div className="flex min-w-0 flex-1 flex-col gap-2">
            <div className="h-4 w-[85%] max-w-[11rem] rounded bg-slate-700" />
            <div className="h-3 w-[60%] max-w-[9rem] rounded bg-slate-700/55" />
            <div className="mt-auto flex flex-wrap gap-2">
              <span className="rounded-md bg-emerald-500/20 px-2 py-1 text-[10px] font-semibold uppercase text-emerald-300">
                New
              </span>
            </div>
            <div className="mt-1 h-8 rounded-lg bg-indigo-600/90 text-center text-xs leading-8 text-white">
              Continue
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
