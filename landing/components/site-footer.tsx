import Link from "next/link";
import { Heart } from "lucide-react";
import {
  authorName,
  bugReportUrl,
  extensionPrivacyHref,
  githubUrl,
} from "@/lib/site-config";

export function SiteFooter() {
  const year = new Date().getFullYear();
  return (
    <footer className="border-t border-[var(--color-border)] px-4 py-12 sm:px-6">
      <div className="mx-auto flex max-w-6xl flex-col items-center gap-8 sm:flex-row sm:justify-between">
        <div className="flex flex-wrap justify-center gap-x-6 gap-y-2 text-sm text-[var(--color-muted)]">
          <Link
            href={githubUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="transition hover:text-[var(--color-text)]"
          >
            Repository
          </Link>
          <Link
            href={bugReportUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="transition hover:text-[var(--color-text)]"
          >
            Report an issue
          </Link>
          <Link
            href={extensionPrivacyHref}
            target="_blank"
            rel="noopener noreferrer"
            className="transition hover:text-[var(--color-text)]"
          >
            Extension privacy
          </Link>
        </div>
        <p className="flex items-center gap-2 text-sm text-[var(--color-muted)]">
          <Heart className="h-4 w-4 shrink-0 text-[var(--color-accent)]/80" aria-hidden />
          Built by {authorName} · © {year} Manga Watchlist
        </p>
      </div>
      <p className="mx-auto mt-8 max-w-2xl text-center text-xs leading-relaxed text-[var(--color-muted)]">
        Covers load from external sites for artwork; those hosts may see your IP when
        the app fetches images. Chromium is a trademark of Google LLC.
      </p>
    </footer>
  );
}
