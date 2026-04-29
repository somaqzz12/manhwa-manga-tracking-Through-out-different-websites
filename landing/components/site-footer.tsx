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
    <footer className="border-t border-white/[0.06] px-4 py-12 sm:px-6">
      <div className="mx-auto flex max-w-6xl flex-col items-center gap-8 sm:flex-row sm:justify-between">
        <div className="flex flex-wrap justify-center gap-x-6 gap-y-2 text-sm text-slate-400">
          <Link
            href={githubUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="transition hover:text-white"
          >
            Repository
          </Link>
          <Link
            href={bugReportUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="transition hover:text-white"
          >
            Report an issue
          </Link>
          <Link
            href={extensionPrivacyHref}
            target="_blank"
            rel="noopener noreferrer"
            className="transition hover:text-white"
          >
            Extension privacy
          </Link>
        </div>
        <p className="flex items-center gap-2 text-sm text-slate-500">
          <Heart className="h-4 w-4 shrink-0 text-indigo-500/80" aria-hidden />
          Built by {authorName} · © {year} Zero Hour
        </p>
      </div>
      <p className="mx-auto mt-8 max-w-2xl text-center text-xs leading-relaxed text-slate-600">
        Covers load from external sites for artwork; those hosts may see your IP when
        the app fetches images. Chromium is a trademark of Google LLC.
      </p>
    </footer>
  );
}
