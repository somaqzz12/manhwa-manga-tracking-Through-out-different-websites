import Link from "next/link";
import {
  dashboardUrl,
  extensionZipDownloadUrl,
  webStoreUrl,
} from "@/lib/site-config";

export function Hero() {
  const appHref =
    dashboardUrl.length > 0
      ? `${dashboardUrl.replace(/\/$/, "")}/dashboard`
      : "https://api.mangawatchlist.space/dashboard";

  return (
    <section className="section px-10 pb-28 pt-16 sm:px-12 md:px-16 max-w-6xl">
      <h1 className="font-serif text-[clamp(2.75rem,8vw,4.5rem)] leading-[1.1] mb-8 text-[var(--color-text)] tracking-tight">
        Track what you read,
        <br /> beautifully.
      </h1>
      <p className="text-xl text-[var(--color-muted)] mb-14 max-w-xl leading-relaxed">
        A clean, minimal way to manage your manga and manhwa.
      </p>
      <div className="flex flex-wrap items-center gap-4">
        <a
          href={appHref}
          className="btn-primary inline-flex items-center justify-center px-8 py-3.5 text-sm font-medium rounded-full text-white no-underline transition duration-200 hover:-translate-y-0.5"
        >
          Open Live App
        </a>
        <a
          href={extensionZipDownloadUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="btn-glass inline-flex items-center justify-center px-8 py-3.5 text-sm font-medium rounded-full text-[var(--color-text)] no-underline transition duration-200 hover:-translate-y-0.5"
        >
          Download extension (ZIP)
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
      <p className="mt-5 max-w-lg text-sm leading-relaxed text-[var(--color-muted)]">
        Unzip the file, open{" "}
        <code className="rounded-md bg-[color-mix(in_srgb,var(--color-text)_6%,transparent)] px-1.5 py-0.5 text-[0.8em]">
          chrome://extensions
        </code>
        , enable <strong>Developer mode</strong>, then <strong>Load unpacked</strong> and select the
        extracted folder (the one that contains <code className="text-[0.85em]">manifest.json</code>
        ).
      </p>
    </section>
  );
}
