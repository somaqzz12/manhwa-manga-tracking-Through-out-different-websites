import type { Metadata } from "next";
import Link from "next/link";
import { SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";
import { dashboardUrl, extensionZipDownloadUrl } from "@/lib/site-config";

export const metadata: Metadata = {
  title: "Browser extension — Manga Watchlist",
  description:
    "Track manga from sites you already use. Detect reader pages, sync safe metadata, mark chapters read. Install steps, permissions, and privacy.",
};

function MiniCard({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
      <p className="text-xs font-bold uppercase tracking-wider text-[var(--color-muted)]">{label}</p>
      <p className="mt-2 text-sm leading-relaxed text-[var(--color-muted)]">{children}</p>
    </div>
  );
}

function PermItem({ name, children }: { name: string; children: React.ReactNode }) {
  return (
    <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface-2)] p-4">
      <p className="font-mono text-sm font-bold text-[var(--color-text)]">{name}</p>
      <p className="mt-2 text-sm leading-relaxed text-[var(--color-muted)]">{children}</p>
    </div>
  );
}

export default function ExtensionPage() {
  const base = dashboardUrl.replace(/\/$/, "");

  return (
    <div className="min-h-screen bg-background">
      <SiteHeader />
      <main>
        <section className="mx-auto max-w-6xl px-4 pb-16 pt-10 sm:px-8 md:px-12">
          <div className="rounded-[28px] border border-[var(--color-border)] bg-[var(--color-surface)] p-8 shadow-sm md:p-10">
            <h1 className="font-serif text-[clamp(1.85rem,4vw,2.65rem)] leading-[1.08] text-[var(--color-text)]">
              Track manga from the sites you already use.
            </h1>
            <p className="mt-5 max-w-3xl text-lg leading-relaxed text-[var(--color-muted)]">
              The Manga Watchlist extension detects the page you&apos;re reading, sends safe metadata to your library, and
              helps you mark chapters as read — without hosting manga chapters or panels.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <a
                href={extensionZipDownloadUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="btn-primary inline-flex rounded-full px-7 py-3.5 text-sm font-semibold no-underline"
              >
                Download extension ZIP
              </a>
              <a
                href="#install"
                className="btn-glass inline-flex rounded-full px-7 py-3.5 text-sm font-semibold text-[var(--color-text)] no-underline"
              >
                View instructions
              </a>
            </div>
          </div>
        </section>

        <section className="border-t border-[var(--color-border)] px-4 py-14 sm:px-8 md:px-12" id="what-it-does">
          <div className="mx-auto max-w-6xl">
            <p className="mb-2 text-xs font-bold uppercase tracking-wider text-[var(--color-muted)]">What it does</p>
            <h2 className="font-serif text-2xl font-bold text-[var(--color-text)] sm:text-3xl">Built for readers who live in the browser</h2>
            <div className="mt-8 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              <MiniCard label="Detect">Recognizes many reader and series pages so you don&apos;t have to copy URLs by hand.</MiniCard>
              <MiniCard label="Library">Adds entries to your Manga Watchlist library with title, URL, and chapter hints.</MiniCard>
              <MiniCard label="Progress">Mark chapters read and keep the dashboard in sync with what you opened.</MiniCard>
              <MiniCard label="Fallback">When auto-detection misses, paste or edit details manually — you&apos;re still covered.</MiniCard>
              <MiniCard label="Requests">Surface sites that need better support and align with the project&apos;s source-request flow.</MiniCard>
              <MiniCard label="Mini tracker">Optional floating helpers and shortcuts so tracking stays one click away.</MiniCard>
            </div>
          </div>
        </section>

        <section className="border-t border-[var(--color-border)] bg-[var(--color-surface-2)] px-4 py-14 sm:px-8 md:px-12" id="how-it-works">
          <div className="mx-auto max-w-6xl">
            <p className="mb-2 text-xs font-bold uppercase tracking-wider text-[var(--color-muted)]">How it works</p>
            <h2 className="font-serif text-2xl font-bold text-[var(--color-text)] sm:text-3xl">From a tab to your library</h2>
            <ol className="mt-8 max-w-2xl list-decimal space-y-4 pl-6 text-[var(--color-muted)] marker:font-semibold marker:text-[var(--color-accent)]">
              <li>
                <strong className="text-[var(--color-text)]">Visit</strong> a manga or manhwa page in your browser.
              </li>
              <li>
                <strong className="text-[var(--color-text)]">Open</strong> the Manga Watchlist extension (toolbar icon).
              </li>
              <li>
                <strong className="text-[var(--color-text)]">Preview</strong> the detected title, URL, and chapter metadata.
              </li>
              <li>
                <strong className="text-[var(--color-text)]">Add</strong> it to your library or update progress.
              </li>
              <li>
                <strong className="text-[var(--color-text)]">Continue</strong> in the dashboard — checks, lists, and source comparison stay
                centralized.
              </li>
            </ol>
          </div>
        </section>

        <section className="border-t border-[var(--color-border)] px-4 py-14 sm:px-8 md:px-12" id="safety">
          <div className="mx-auto max-w-6xl">
            <p className="mb-2 text-xs font-bold uppercase tracking-wider text-[var(--color-muted)]">Safety &amp; privacy</p>
            <h2 className="font-serif text-2xl font-bold text-[var(--color-text)] sm:text-3xl">What we never do</h2>
            <ul className="mt-8 max-w-3xl list-disc space-y-3 pl-6 text-[var(--color-muted)]">
              <li>
                <strong className="text-[var(--color-text)]">No full-page upload.</strong> The extension does not send complete HTML documents to
                our servers.
              </li>
              <li>
                <strong className="text-[var(--color-text)]">No panel pipeline.</strong> It does not fetch, cache, or proxy manga panels or chapter
                images for reading.
              </li>
              <li>
                <strong className="text-[var(--color-text)]">No bypass.</strong> It does not circumvent paywalls, logins, bot checks, Cloudflare
                challenges, DRM, or private APIs.
              </li>
              <li>
                <strong className="text-[var(--color-text)]">Metadata only.</strong> When syncing, expect URL-level fields such as title, page URL,
                source domain, chapter number when detected, and cover URL if the page exposes one safely.
              </li>
            </ul>
          </div>
        </section>

        <section className="border-t border-[var(--color-border)] bg-[var(--color-surface-2)] px-4 py-14 sm:px-8 md:px-12" id="install">
          <div className="mx-auto max-w-6xl">
            <p className="mb-2 text-xs font-bold uppercase tracking-wider text-[var(--color-muted)]">Install</p>
            <h2 className="font-serif text-2xl font-bold text-[var(--color-text)] sm:text-3xl">Chrome — manual install (unpacked)</h2>
            <p className="mt-4 max-w-3xl text-[var(--color-muted)] leading-relaxed">
              The extension is distributed as source for developer-mode loading. Download the ZIP, unzip, then load the folder that contains{" "}
              <code className="rounded-md bg-[color-mix(in_srgb,var(--color-text)_6%,transparent)] px-1.5 py-0.5 text-[0.85em]">
                manifest.json
              </code>
              .
            </p>
            <ol className="mt-8 max-w-3xl list-decimal space-y-4 pl-6 text-[var(--color-muted)] marker:font-semibold">
              <li>
                <strong className="text-[var(--color-text)]">Download</strong> the{" "}
                <a href={extensionZipDownloadUrl} target="_blank" rel="noopener noreferrer" className="font-semibold text-[var(--color-accent)]">
                  extension ZIP
                </a>{" "}
                and unzip it on your computer.
              </li>
              <li>
                Open{" "}
                <code className="rounded-md bg-[color-mix(in_srgb,var(--color-text)_6%,transparent)] px-1.5 py-0.5 text-[0.85em]">
                  chrome://extensions
                </code>{" "}
                (or{" "}
                <code className="rounded-md bg-[color-mix(in_srgb,var(--color-text)_6%,transparent)] px-1.5 py-0.5 text-[0.85em]">
                  edge://extensions
                </code>{" "}
                in Microsoft Edge).
              </li>
              <li>
                Enable <strong className="text-[var(--color-text)]">Developer mode</strong>.
              </li>
              <li>
                Click <strong className="text-[var(--color-text)]">Load unpacked</strong>.
              </li>
              <li>
                Select the unzipped folder that contains{" "}
                <code className="rounded-md bg-[color-mix(in_srgb,var(--color-text)_6%,transparent)] px-1.5 py-0.5 text-[0.85em]">
                  manifest.json
                </code>{" "}
                (not a parent directory).
              </li>
            </ol>
            <div className="mt-8 flex flex-wrap gap-3">
              <a
                href={extensionZipDownloadUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="btn-primary inline-flex rounded-full px-6 py-3 text-sm font-semibold no-underline"
              >
                Download extension ZIP
              </a>
              <Link href="/" className="btn-glass inline-flex rounded-full px-6 py-3 text-sm font-semibold text-[var(--color-text)] no-underline">
                Back to home
              </Link>
            </div>
          </div>
        </section>

        <section className="border-t border-[var(--color-border)] px-4 py-14 sm:px-8 md:px-12" id="permissions">
          <div className="mx-auto max-w-6xl">
            <p className="mb-2 text-xs font-bold uppercase tracking-wider text-[var(--color-muted)]">Permissions</p>
            <h2 className="font-serif text-2xl font-bold text-[var(--color-text)] sm:text-3xl">Why the extension asks for these</h2>
            <p className="mt-4 max-w-3xl text-[var(--color-muted)] leading-relaxed">
              Plain-language summary of the permissions declared in the extension manifest.
            </p>
            <div className="mt-8 grid gap-3 md:grid-cols-2">
              <PermItem name="activeTab">
                Lets the extension read basic information about the tab when you click the icon or run a command — only for that active tab, not
                your whole history.
              </PermItem>
              <PermItem name="storage">Keeps local settings and small pieces of state (for example preferences) on your device.</PermItem>
              <PermItem name="tabs">Finds or focuses your dashboard tab and coordinates navigation between reader pages and the app.</PermItem>
              <PermItem name="alarms">Schedules lightweight background timers for reminders or periodic housekeeping in the service worker.</PermItem>
              <PermItem name="contextMenus">Adds optional right-click entries so you can act on the current page quickly.</PermItem>
              <PermItem name="scripting">
                Injects the content helper only on supported reader domains so structured metadata (title, chapter hints) can be read — still
                subject to the safety rules above.
              </PermItem>
            </div>
          </div>
        </section>

        <section className="border-t border-[var(--color-border)] px-4 py-10 sm:px-8 md:px-12">
          <div className="mx-auto max-w-3xl text-center text-sm text-[var(--color-muted)]">
            <p>
              Manga Watchlist does not host chapters or panels. Covers and metadata may load from third-party hosts.
            </p>
            <p className="mt-4">
              <Link href="/" className="font-semibold text-[var(--color-accent)] no-underline hover:underline">
                Home
              </Link>
              {" · "}
              <a href={`${base}/discover`} className="font-semibold text-[var(--color-accent)] no-underline hover:underline">
                Discover
              </a>
            </p>
          </div>
        </section>
      </main>
      <SiteFooter />
    </div>
  );
}
