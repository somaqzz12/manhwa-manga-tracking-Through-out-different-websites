import { Hero } from "@/components/hero";
import { MangaShowcaseSection } from "@/components/manga-showcase";
import { SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";
import {
  demoPopularManga,
  demoPopularManhwa,
  demoRecentRows,
  demoTrendingWeek,
} from "@/lib/landing-demo";
import { dashboardUrl, extensionZipDownloadUrl } from "@/lib/site-config";

export default function HomePage() {
  const base = dashboardUrl.replace(/\/$/, "");

  return (
    <div className="min-h-screen bg-background">
      <SiteHeader />
      <main>
        <Hero />
        <MangaShowcaseSection
          kicker="Featured examples"
          title="Trending this week"
          subtitle="Illustrative picks for the homepage — not live charts or rankings."
          cards={demoTrendingWeek}
          columns="dense"
        />
        <MangaShowcaseSection
          kicker="Featured examples"
          title="Popular manhwa"
          cards={demoPopularManhwa}
        />
        <MangaShowcaseSection
          kicker="Featured examples"
          title="Popular manga"
          cards={demoPopularManga}
        />

        <section className="border-t border-[var(--color-border)] px-4 py-14 sm:px-8 md:px-12">
          <div className="mx-auto max-w-6xl">
            <p className="mb-2 text-xs font-bold uppercase tracking-wider text-[var(--color-muted)]">Featured examples</p>
            <h2 className="font-serif text-2xl font-bold text-[var(--color-text)] sm:text-3xl">Recently updated</h2>
            <p className="mt-2 text-[var(--color-muted)]">Sample rows — not a live feed.</p>
            <div className="mt-6 overflow-x-auto rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)]">
              <table className="w-full min-w-[480px] text-left text-sm">
                <thead>
                  <tr className="border-b border-[var(--color-border)] text-xs font-semibold uppercase tracking-wider text-[var(--color-muted)]">
                    <th className="px-4 py-3">Title</th>
                    <th className="px-4 py-3">Source</th>
                    <th className="px-4 py-3">Latest</th>
                    <th className="px-4 py-3">Status</th>
                  </tr>
                </thead>
                <tbody className="text-[var(--color-text)]">
                  {demoRecentRows.map((row) => (
                    <tr key={row.title} className="border-b border-[color-mix(in_srgb,var(--color-border)_70%,transparent)] last:border-0">
                      <td className="px-4 py-3">{row.title}</td>
                      <td className="px-4 py-3">{row.source}</td>
                      <td className="px-4 py-3">{row.chapter}</td>
                      <td className="px-4 py-3 text-[var(--color-muted)]">{row.status}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </section>

        <section className="border-t border-[var(--color-border)] px-4 py-14 sm:px-8 md:px-12 bg-[var(--color-surface-2)]">
          <div className="mx-auto max-w-6xl">
            <h2 className="font-serif text-2xl font-bold text-[var(--color-text)] sm:text-3xl">Where should I track Solo Leveling?</h2>
            <p className="mt-3 max-w-2xl text-[var(--color-muted)]">
              Source comparison is the heart of the product — same title, different sites, different support levels.
            </p>
            <div className="mt-6 overflow-x-auto rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)]">
              <table className="w-full min-w-[520px] text-left text-sm">
                <thead>
                  <tr className="border-b border-[var(--color-border)] text-xs font-semibold uppercase tracking-wider text-[var(--color-muted)]">
                    <th className="px-4 py-3">Source</th>
                    <th className="px-4 py-3">Support</th>
                    <th className="px-4 py-3">Notes</th>
                  </tr>
                </thead>
                <tbody>
                  <tr className="border-b border-[color-mix(in_srgb,var(--color-border)_70%,transparent)]">
                    <td className="px-4 py-3">MangaDex</td>
                    <td className="px-4 py-3">Automatic</td>
                    <td className="px-4 py-3 text-[var(--color-muted)]">Public metadata &amp; catalog API</td>
                  </tr>
                  <tr className="border-b border-[color-mix(in_srgb,var(--color-border)_70%,transparent)]">
                    <td className="px-4 py-3">WEBTOON</td>
                    <td className="px-4 py-3">Manual</td>
                    <td className="px-4 py-3 text-[var(--color-muted)]">Official publisher site — track the URL yourself</td>
                  </tr>
                  <tr className="border-b border-[color-mix(in_srgb,var(--color-border)_70%,transparent)]">
                    <td className="px-4 py-3">Asura</td>
                    <td className="px-4 py-3">Manual only</td>
                    <td className="px-4 py-3 text-[var(--color-muted)]">User-added mirror — auto checks may be limited</td>
                  </tr>
                  <tr>
                    <td className="px-4 py-3">Unknown site</td>
                    <td className="px-4 py-3">Requested</td>
                    <td className="px-4 py-3 text-[var(--color-muted)]">Future adapter — request from Source Requests</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <p className="mt-4 rounded-2xl border border-[color-mix(in_srgb,var(--color-accent)_28%,var(--color-border))] bg-[color-mix(in_srgb,var(--color-accent)_8%,var(--color-surface-2))] px-4 py-3 text-sm font-semibold text-[var(--color-text)]">
              Recommended: <span className="text-[var(--color-accent)]">MangaDex</span> for automatic chapter checks when healthy.
            </p>
          </div>
        </section>

        <section className="border-t border-[var(--color-border)] px-4 py-14 sm:px-8 md:px-12">
          <div className="mx-auto max-w-6xl">
            <h2 className="font-serif text-2xl font-bold text-[var(--color-text)]">Supported sources</h2>
            <p className="mt-2 max-w-2xl text-[var(--color-muted)]">
              Automatic adapters, experimental detection, and manual bookmarks — every URL is still accepted.
            </p>
            <div className="mt-6 grid gap-3 sm:grid-cols-3">
              <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface-2)] p-4">
                <p className="text-xs font-bold uppercase tracking-wider text-[var(--color-muted)]">Automatic</p>
                <p className="mt-2 text-sm text-[var(--color-muted)]">
                  MangaDex, MANGA Plus, ComicWalker, and other API-backed catalogs.
                </p>
              </div>
              <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface-2)] p-4">
                <p className="text-xs font-bold uppercase tracking-wider text-[var(--color-muted)]">Supported</p>
                <p className="mt-2 text-sm text-[var(--color-muted)]">
                  Popular readers with dedicated parsers — see the live Sources page.
                </p>
              </div>
              <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface-2)] p-4">
                <p className="text-xs font-bold uppercase tracking-wider text-[var(--color-muted)]">Manual &amp; requests</p>
                <p className="mt-2 text-sm text-[var(--color-muted)]">
                  Paste any listing URL; request new domains when you need adapters.
                </p>
              </div>
            </div>
            <div className="mt-6 flex flex-wrap gap-3">
              <a
                href={`${base}/sources`}
                className="btn-primary inline-flex rounded-full px-6 py-3 text-sm font-semibold no-underline"
              >
                Browse sources
              </a>
              <a
                href={`${base}/source-requests`}
                className="btn-glass inline-flex rounded-full px-6 py-3 text-sm font-semibold text-[var(--color-text)] no-underline"
              >
                Source requests
              </a>
            </div>
          </div>
        </section>

        <section id="extension" className="border-t border-[var(--color-border)] px-4 py-14 sm:px-8 md:px-12 bg-[var(--color-surface-2)]">
          <div className="mx-auto max-w-6xl">
            <h2 className="font-serif text-2xl font-bold text-[var(--color-text)]">Track from any site with the extension</h2>
            <p className="mt-3 max-w-2xl text-[var(--color-muted)] leading-relaxed">
              Detect the page you&apos;re reading, send it to your library, and mark chapters as read — optional companion to
              the website.
            </p>
            <div className="mt-6 flex flex-wrap gap-3">
              <a
                href={extensionZipDownloadUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="btn-primary inline-flex rounded-full px-6 py-3 text-sm font-semibold no-underline"
              >
                Download extension
              </a>
              <a href={`${base}/app`} className="btn-glass inline-flex rounded-full px-6 py-3 text-sm font-semibold text-[var(--color-text)] no-underline">
                Open app
              </a>
            </div>
          </div>
        </section>

        <section className="border-t border-[var(--color-border)] px-4 py-14 sm:px-8 md:px-12">
          <div className="mx-auto max-w-3xl text-center">
            <h2 className="font-serif text-2xl font-bold text-[var(--color-text)]">Safety</h2>
            <p className="mt-4 text-[var(--color-muted)] leading-relaxed">
              <strong className="text-[var(--color-text)]">We do not host chapters or panels.</strong> Manga Watchlist stores
              metadata, URLs, and your reading progress — not reader pages or panel images.
            </p>
          </div>
        </section>
      </main>
      <SiteFooter />
    </div>
  );
}
