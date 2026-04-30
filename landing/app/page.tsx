import { FeatureGrid } from "@/components/feature-grid";
import { Hero } from "@/components/hero";
import { HowItWorks } from "@/components/how-it-works";
import { SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";
import { dashboardUrl } from "@/lib/site-config";

export default function HomePage() {
  const base = dashboardUrl.replace(/\/$/, "");

  return (
    <div className="min-h-screen bg-grid-fade bg-background">
      <SiteHeader />
      <main>
        <Hero />
        <section className="border-t border-[var(--color-border)] px-4 py-16 sm:px-8 md:px-12">
          <div className="mx-auto max-w-6xl">
            <h2 className="font-serif text-2xl font-bold tracking-tight text-[var(--color-text)] sm:text-3xl">
              Example source comparison
            </h2>
            <p className="mt-3 max-w-2xl text-[var(--color-muted)]">
              Same story can read differently across hosts — compare latest chapter hints before you commit
              to a site.
            </p>
            <div className="mt-8 overflow-x-auto rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)]">
              <table className="w-full min-w-[520px] text-left text-sm">
                <thead>
                  <tr className="border-b border-[var(--color-border)] text-xs font-semibold uppercase tracking-wider text-[var(--color-muted)]">
                    <th className="px-4 py-3">Source</th>
                    <th className="px-4 py-3">Latest</th>
                    <th className="px-4 py-3">Note</th>
                    <th className="px-4 py-3">Support</th>
                  </tr>
                </thead>
                <tbody className="text-[var(--color-text)]">
                  <tr className="border-b border-[color-mix(in_srgb,var(--color-border)_70%,transparent)]">
                    <td className="px-4 py-3">Asura</td>
                    <td className="px-4 py-3">Ch. 179</td>
                    <td className="px-4 py-3 text-[var(--color-muted)]">Fast fan updates</td>
                    <td className="px-4 py-3">Supported</td>
                  </tr>
                  <tr className="border-b border-[color-mix(in_srgb,var(--color-border)_70%,transparent)]">
                    <td className="px-4 py-3">Reaper</td>
                    <td className="px-4 py-3">Ch. 178</td>
                    <td className="px-4 py-3 text-[var(--color-muted)]">Backup mirror</td>
                    <td className="px-4 py-3">Supported</td>
                  </tr>
                  <tr className="border-b border-[color-mix(in_srgb,var(--color-border)_70%,transparent)]">
                    <td className="px-4 py-3">MangaDex</td>
                    <td className="px-4 py-3">Ch. 200</td>
                    <td className="px-4 py-3 text-[var(--color-muted)]">Public catalog</td>
                    <td className="px-4 py-3">Automatic</td>
                  </tr>
                  <tr>
                    <td className="px-4 py-3">Unknown</td>
                    <td className="px-4 py-3">Manual</td>
                    <td className="px-4 py-3 text-[var(--color-muted)]">User-added URL</td>
                    <td className="px-4 py-3">Manual</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </section>
        <section className="border-t border-[var(--color-border)] px-4 py-16 sm:px-8 md:px-12 bg-[var(--color-surface-2)]">
          <div className="mx-auto max-w-6xl grid gap-8 md:grid-cols-2">
            <div>
              <h2 className="font-serif text-2xl font-bold text-[var(--color-text)]">Featured examples</h2>
              <p className="mt-2 text-[var(--color-muted)]">
                Static demo titles for layout — not live rankings or analytics.
              </p>
              <ul className="mt-4 space-y-2 text-sm text-[var(--color-muted)]">
                <li>Solo Leveling · Tower of God · Omniscient Reader</li>
                <li>One Piece · Jujutsu Kaisen · Chainsaw Man</li>
              </ul>
            </div>
            <div>
              <h2 className="font-serif text-2xl font-bold text-[var(--color-text)]">Extension companion</h2>
              <p className="mt-2 text-[var(--color-muted)] leading-relaxed">
                Optional Chrome extension detects open chapters and syncs progress to your account. Discovery,
                comparison, and your library stay on the website.
              </p>
              <a
                href={`${base}/sources`}
                className="mt-4 inline-flex text-sm font-semibold text-[var(--color-accent)] underline-offset-4 hover:underline"
              >
                View source support →
              </a>
            </div>
          </div>
        </section>
        <FeatureGrid />
        <HowItWorks />
        <section className="border-t border-[var(--color-border)] px-4 py-16 sm:px-8 md:px-12">
          <div className="mx-auto max-w-3xl text-center">
            <h2 className="font-serif text-2xl font-bold text-[var(--color-text)]">Safety</h2>
            <p className="mt-4 text-[var(--color-muted)] leading-relaxed">
              <strong className="text-[var(--color-text)]">We do not host chapters or panel images.</strong>{" "}
              Manga Watchlist stores metadata, URLs, and your reading progress — never a reader cache or image
              proxy.
            </p>
          </div>
        </section>
      </main>
      <SiteFooter />
    </div>
  );
}
