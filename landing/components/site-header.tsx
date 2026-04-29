import Link from "next/link";
import { ChromeIcon } from "@/components/chrome-icon";
import { githubUrl, webStoreUrl } from "@/lib/site-config";

function primaryCta() {
  const label =
    webStoreUrl.length > 0 ? "Add to Chrome" : "Extension source";
  const href =
    webStoreUrl.length > 0
      ? webStoreUrl
      : `${githubUrl}/tree/main/extension`;
  const external = true;
  return (
    <Link
      href={href}
      className="inline-flex items-center gap-2 rounded-full bg-gradient-to-br from-indigo-500 to-indigo-600 px-4 py-2 text-sm font-semibold text-white shadow-accent outline-none ring-1 ring-white/15 transition hover:from-indigo-400 hover:to-indigo-500 focus-visible:ring-2 focus-visible:ring-indigo-400"
      {...(external ? { target: "_blank", rel: "noopener noreferrer" } : {})}
      aria-label={label}
    >
      <ChromeIcon className="h-5 w-5 text-white" />
      {label}
    </Link>
  );
}

export function SiteHeader() {
  return (
    <header className="sticky top-0 z-50 border-b border-white/[0.07] bg-background/85 backdrop-blur-md">
      <div className="mx-auto flex h-14 max-w-6xl items-center justify-between px-4 sm:px-6">
        <Link href="/" className="flex items-center gap-2 font-semibold text-white">
          <span
            className="grid size-9 place-items-center rounded-xl bg-gradient-to-br from-indigo-400 to-indigo-600 text-sm font-bold shadow-accent"
            aria-hidden
          >
            MW
          </span>
          <span className="tracking-tight">Manga Watchlist</span>
        </Link>
        <div className="flex items-center gap-3">
          <Link
            href={githubUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="hidden text-sm font-medium text-slate-400 transition hover:text-white sm:inline"
          >
            GitHub
          </Link>
          {primaryCta()}
        </div>
      </div>
    </header>
  );
}
