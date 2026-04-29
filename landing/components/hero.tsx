import Link from "next/link";
import { ExternalLink } from "lucide-react";
import { ChromeIcon } from "@/components/chrome-icon";
import { dashboardUrl, githubUrl, webStoreUrl } from "@/lib/site-config";

export function Hero() {
  const storeHref =
    webStoreUrl.length > 0
      ? webStoreUrl
      : `${githubUrl}/tree/main/extension`;

  const isStore = webStoreUrl.length > 0;

  return (
    <section className="relative px-4 pb-24 pt-16 sm:px-6 lg:pb-28 lg:pt-20">
      <div className="mx-auto flex max-w-6xl flex-col items-center gap-12 lg:flex-row lg:items-center lg:justify-between lg:gap-16">
        <div className="max-w-xl text-center lg:text-left">
          <p className="mb-4 inline-flex items-center gap-2 rounded-full border border-indigo-500/25 bg-indigo-500/10 px-3 py-1 text-xs font-semibold uppercase tracking-wider text-indigo-300">
            Web app · Chrome extension
          </p>
          <h1 className="bg-gradient-to-b from-white to-slate-300 bg-clip-text text-4xl font-bold tracking-tight text-transparent sm:text-5xl lg:text-[3.25rem] lg:leading-[1.1]">
            Hit zero unread, anywhere you read.
          </h1>
          <p className="mt-5 text-lg text-slate-400 sm:text-xl">
            Zero Hour is a manga and manhwa tracker. Sign up with a username and
            password, add series from any listing URL, and open your dashboard from
            anywhere. The Chrome extension captures the chapter you’re reading so
            unread counts and one-click Continue stay accurate on your account.
          </p>
          <div className="mt-10 flex flex-col items-stretch gap-3 sm:flex-row sm:flex-wrap sm:items-center lg:justify-start">
            <Link
              href={storeHref}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex min-h-[3.25rem] items-center justify-center gap-2 rounded-full bg-gradient-to-br from-indigo-500 to-violet-600 px-8 py-3.5 text-base font-semibold text-white shadow-accentLg outline-none ring-1 ring-white/15 transition hover:from-indigo-400 hover:to-violet-500 focus-visible:ring-2 focus-visible:ring-indigo-400"
              aria-label={isStore ? "Add Zero Hour to Chrome" : "Open extension source on GitHub"}
            >
              <ChromeIcon className="h-7 w-7 shrink-0 text-white" />
              {isStore ? "Add to Chrome" : "Get extension (GitHub)"}
            </Link>
            {dashboardUrl.length > 0 ? (
              <Link
                href={dashboardUrl}
                className="inline-flex min-h-[3.25rem] items-center justify-center gap-2 rounded-full border border-slate-600/80 bg-card px-8 py-3.5 text-base font-semibold text-slate-100 transition hover:border-indigo-500/50 hover:bg-slate-800/80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
              >
                Open live app
                <ExternalLink className="h-4 w-4 opacity-70" aria-hidden />
              </Link>
            ) : (
              <Link
                href={`${githubUrl}#readme`}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex min-h-[3.25rem] items-center justify-center gap-2 rounded-full border border-slate-600/80 bg-card px-8 py-3.5 text-base font-semibold text-slate-100 transition hover:border-indigo-500/50 hover:bg-slate-800/80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
              >
                Read the docs
                <ExternalLink className="h-4 w-4 opacity-70" aria-hidden />
              </Link>
            )}
          </div>
          {!isStore && (
            <p className="mt-4 text-sm text-amber-200/85">
              Set{" "}
              <code className="rounded bg-slate-800/80 px-1.5 py-0.5 text-indigo-200">
                NEXT_PUBLIC_WEB_STORE_URL
              </code>{" "}
              when your Chrome Web Store listing is live — the primary button will link
              there instead.
            </p>
          )}
        </div>
        <HeroVisual />
      </div>
    </section>
  );
}

/** Decorative mini-preview evocative of popup + dash without external assets. */
function HeroVisual() {
  return (
    <div className="relative w-full max-w-md shrink-0 lg:max-w-lg">
      <div className="absolute -left-10 -top-10 h-40 w-40 rounded-full bg-indigo-500/20 blur-3xl" />
      <div className="absolute -bottom-6 -right-6 h-32 w-32 rounded-full bg-cyan-500/15 blur-3xl" />
      <div className="relative rounded-2xl border border-slate-700/80 bg-card p-4 shadow-accentLg ring-1 ring-white/5">
          <div className="mb-3 flex items-center justify-between border-b border-slate-700/60 pb-3">
          <div className="flex items-center gap-2">
            <span className="grid size-8 place-items-center rounded-lg bg-gradient-to-br from-indigo-400 to-indigo-600 text-xs font-bold text-white">
              ZH
            </span>
            <span className="text-sm font-semibold text-white">Zero Hour</span>
          </div>
          <span className="flex items-center gap-1.5 text-xs font-medium text-emerald-400">
            <span className="size-2 rounded-full bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.8)]" />
            Connected
          </span>
        </div>
        <div className="grid gap-2">
          <div className="rounded-xl border border-slate-700/60 bg-[#0b1220] p-3">
            <p className="text-[10px] font-bold uppercase tracking-widest text-cyan-300/95">
              Unread chapters
            </p>
            <p className="mt-1 text-3xl font-bold tabular-nums text-white">126</p>
          </div>
          <div className="rounded-xl border border-slate-700/60 bg-[#0b1220] p-3">
            <p className="text-[10px] font-bold uppercase tracking-widest text-slate-500">
              No chapter detected
            </p>
            <p className="mt-2 text-xs leading-relaxed text-slate-400">
              Open a chapter page — the popup picks it up automatically.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
