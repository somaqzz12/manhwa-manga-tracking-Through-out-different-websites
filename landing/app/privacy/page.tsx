import type { Metadata } from "next";
import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";
import { githubUrl } from "@/lib/site-config";

export const metadata: Metadata = {
  title: "Privacy Policy — Manga Watchlist Companion",
  description:
    "What the Manga Watchlist browser extension stores, what it sends, and the permissions it uses.",
};

export default function PrivacyPage() {
  return (
    <div className="min-h-screen">
      <SiteHeader />
      <main className="px-4 py-16 sm:px-6">
        <article className="mx-auto max-w-3xl">
          <Link
            href="/"
            className="mb-8 inline-flex items-center gap-2 text-sm text-slate-400 transition hover:text-white"
          >
            <ArrowLeft className="h-4 w-4" aria-hidden /> Back to home
          </Link>

          <h1 className="bg-gradient-to-b from-white to-slate-300 bg-clip-text text-4xl font-bold tracking-tight text-transparent sm:text-5xl">
            Privacy Policy
          </h1>
          <p className="mt-3 text-sm text-slate-500">
            Manga Watchlist Companion (Chrome extension) · Last updated April 29, 2026
          </p>

          <div className="prose-content mt-10 space-y-8 text-slate-300">
            <Section title="What the extension does">
              <p>
                The extension helps you sync manga and manhwa <strong>reading progress</strong>{" "}
                to your Manga Watchlist account. By default it talks to the
                official Manga Watchlist server at{" "}
                <code className="text-indigo-200">
                  https://app.mangawatchlist.space
                </code>
                . Advanced users can point the extension at a different deployment
                from the options page. The extension does not host manga content
                or replace a publisher&apos;s website.
              </p>
            </Section>

            <Section title="Data the extension collects">
              <p>
                The extension <strong>does not</strong> sell, rent, or trade personal
                data. It contains <strong>no third-party analytics or advertising
                SDKs</strong>.
              </p>

              <h3 className="mt-6 text-lg font-semibold text-white">
                Stored on your device only
              </h3>
              <ul className="mt-2 list-disc space-y-1 pl-6">
                <li>
                  <strong>Settings</strong> you enter — backend URL, auto-track
                  toggle, prompt cooldown — kept in <code>chrome.storage.local</code>{" "}
                  on your machine.
                </li>
                <li>
                  A small rolling <strong>debug log</strong> of the last 25 sync
                  events, also local-only, to help you troubleshoot.
                </li>
              </ul>

              <h3 className="mt-6 text-lg font-semibold text-white">
                Sent off your device
              </h3>
              <ul className="mt-2 list-disc space-y-1 pl-6">
                <li>
                  <strong>Your Manga Watchlist server only.</strong> When you save
                  progress or refresh the unread badge, requests go to the
                  configured backend URL (default: the official server above).
                  These requests include chapter URLs, series titles, and numeric
                  chapter identifiers needed to update your bookmarks.
                </li>
                <li>
                  <strong>MangaDex (optional, read-only metadata).</strong> On{" "}
                  <code>mangadex.org</code> chapter pages, the extension may call
                  the public <code>api.mangadex.org</code> endpoint to read
                  chapter and series metadata. No MangaDex account is required;
                  no Manga Watchlist credentials are sent to MangaDex.
                </li>
              </ul>

              <p className="mt-4">
                The extension <strong>never</strong> sends your reading activity to
                the extension author or to any other third party.
              </p>
            </Section>

            <Section title="Permissions (why each one exists)">
              <ul className="list-disc space-y-2 pl-6">
                <li>
                  <code>storage</code> — save your backend URL and preferences
                  locally.
                </li>
                <li>
                  <code>activeTab</code> — read the current tab when you use the
                  popup, shortcut, or context menu to track a chapter.
                </li>
                <li>
                  <code>tabs</code> — find the active tab to message the content
                  script and open your dashboard.
                </li>
                <li>
                  <code>alarms</code> — wake the background worker periodically
                  (~30 min) to refresh the unread chapter badge.
                </li>
                <li>
                  <code>contextMenus</code> — provide the &ldquo;Track this manga
                  chapter&rdquo; right-click action.
                </li>
                <li>
                  <strong>Host access (content script <code>&lt;all_urls&gt;</code>)</strong> —
                  manga and manhwa are read on hundreds of independent domains and
                  mirrors. The content script only inspects the page you are on
                  for chapter cues; the extension itself only requests host
                  permission for the configured Manga Watchlist server (and, on
                  MangaDex pages, the public MangaDex API via CORS).
                </li>
              </ul>
            </Section>

            <Section title="Sign-in and session">
              <p>
                You sign in <strong>in the browser</strong> on the Manga Watchlist
                website. The extension reuses that session cookie when calling
                the API, the same way the dashboard would. The extension author
                cannot access your password or session.
              </p>
            </Section>

            <Section title="Your choices">
              <ul className="list-disc space-y-1 pl-6">
                <li>
                  You can <strong>uninstall</strong> the extension at any time;
                  Chrome removes its local storage automatically.
                </li>
                <li>
                  You can <strong>clear local data</strong> from the extension&apos;s
                  Settings page without uninstalling.
                </li>
                <li>
                  You can override the backend URL in Settings to point at your
                  own deployment, or revert to the default.
                </li>
              </ul>
            </Section>

            <Section title="Open source">
              <p>
                The extension source code is available on GitHub at{" "}
                <Link
                  href={githubUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-indigo-300 underline-offset-4 hover:underline"
                >
                  {githubUrl.replace("https://", "")}
                </Link>
                . If you have questions or requests, use the project&apos;s Issues
                page on GitHub.
              </p>
            </Section>
          </div>
        </article>
      </main>
      <SiteFooter />
    </div>
  );
}

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section>
      <h2 className="text-2xl font-semibold tracking-tight text-white">
        {title}
      </h2>
      <div className="mt-3 space-y-3 text-base leading-relaxed text-slate-300">
        {children}
      </div>
    </section>
  );
}
