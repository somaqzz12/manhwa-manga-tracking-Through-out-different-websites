import Link from "next/link";
import {
  dashboardUrl,
  extensionZipDownloadUrl,
  webStoreUrl,
} from "@/lib/site-config";

export function Hero() {
  const base = dashboardUrl.replace(/\/$/, "");
  const discoverSearch = `${base}/discover`;

  return (
    <section className="section px-4 pb-24 pt-14 sm:px-8 md:px-12 max-w-6xl mx-auto">
      <h1 className="font-serif text-[clamp(2rem,6.5vw,3.35rem)] leading-[1.08] mb-6 text-[var(--color-text)] tracking-tight max-w-4xl">
        Search any manga or manhwa. Find the best source. Track updates beautifully.
      </h1>
      <p className="text-lg text-[var(--color-muted)] mb-10 max-w-2xl leading-relaxed">
        Paste any URL or search by title — supported sites resolve automatically; everything else becomes
        intentional manual tracking. The extension is an optional companion for chapter detection.
      </p>

      <div className="rounded-3xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6 md:p-8 shadow-sm mb-10">
        <p className="text-sm font-semibold uppercase tracking-wider text-[var(--color-muted)] mb-4">
          Try it now
        </p>
        <form
          action={discoverSearch}
          method="get"
          className="flex flex-col gap-3 sm:flex-row sm:items-center mb-4"
        >
          <input
            name="q"
            type="search"
            placeholder="Search a title (e.g. Solo Leveling)"
            className="flex-1 min-w-0 rounded-full border border-[var(--color-border)] bg-[var(--color-surface-2)] px-5 py-3.5 text-[var(--color-text)] placeholder:text-[var(--color-muted)] outline-none focus:ring-2 focus:ring-[color-mix(in_srgb,var(--color-accent)_45%,transparent)]"
            aria-label="Search manga or manhwa title"
          />
          <button
            type="submit"
            className="btn-primary shrink-0 rounded-full px-8 py-3.5 text-sm font-semibold transition duration-200 hover:-translate-y-0.5"
          >
            Search titles
          </button>
        </form>
        <form action={discoverSearch} method="get" className="flex flex-col gap-3 sm:flex-row sm:items-center">
          <input
            name="url"
            type="url"
            placeholder="Or paste any series URL — https://…"
            className="flex-1 min-w-0 rounded-full border border-[var(--color-border)] bg-[var(--color-surface-2)] px-5 py-3.5 text-[var(--color-text)] placeholder:text-[var(--color-muted)] outline-none focus:ring-2 focus:ring-[color-mix(in_srgb,var(--color-accent)_45%,transparent)]"
            aria-label="Paste series URL"
          />
          <button
            type="submit"
            className="btn-glass shrink-0 rounded-full px-8 py-3.5 text-sm font-semibold text-[var(--color-text)] transition duration-200 hover:-translate-y-0.5"
          >
            Resolve URL
          </button>
        </form>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <a
          href={`${base}/app/add`}
          className="btn-primary inline-flex items-center justify-center rounded-full px-8 py-3.5 text-sm font-semibold no-underline transition duration-200 hover:-translate-y-0.5"
        >
          Add URL in app
        </a>
        <a
          href={discoverSearch}
          className="btn-glass inline-flex items-center justify-center rounded-full px-8 py-3.5 text-sm font-semibold text-[var(--color-text)] no-underline transition duration-200 hover:-translate-y-0.5"
        >
          Open discover
        </a>
        <a
          href={extensionZipDownloadUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="btn-glass inline-flex items-center justify-center rounded-full px-8 py-3.5 text-sm font-semibold text-[var(--color-text)] no-underline transition duration-200 hover:-translate-y-0.5"
        >
          Extension (ZIP)
        </a>
        {webStoreUrl.length > 0 ? (
          <Link
            href={webStoreUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="text-sm font-medium text-[var(--color-muted)] underline-offset-4 transition hover:text-[var(--color-text)] hover:underline"
          >
            Chrome Web Store →
          </Link>
        ) : null}
      </div>
      <p className="mt-6 max-w-lg text-sm leading-relaxed text-[var(--color-muted)]">
        Unzip the extension, open{" "}
        <code className="rounded-md bg-[color-mix(in_srgb,var(--color-text)_6%,transparent)] px-1.5 py-0.5 text-[0.8em]">
          chrome://extensions
        </code>
        , enable <strong>Developer mode</strong>, then <strong>Load unpacked</strong> and select the
        folder that contains <code className="text-[0.85em]">manifest.json</code>.
      </p>
    </section>
  );
}
