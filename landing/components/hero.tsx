import Link from "next/link";
import { dashboardUrl, webStoreUrl } from "@/lib/site-config";

export function Hero() {
  const appHref = dashboardUrl.length > 0 ? `${dashboardUrl.replace(/\/$/, "")}/dashboard` : "https://api.mangawatchlist.space/dashboard";
  const extensionHref = webStoreUrl.length > 0 ? webStoreUrl : "#";

  return (
    <section className="px-10 py-24 max-w-5xl">
      <h1 className="font-serif text-6xl leading-tight mb-6 text-[var(--color-text)]">
        Track what you read,<br/> beautifully.
      </h1>
      <p className="text-lg text-[var(--color-muted)] mb-10">
        A clean, minimal way to manage your manga and manhwa.
      </p>
      <div className="flex gap-4">
        <a href={appHref} className="px-6 py-3 border border-[var(--color-border)] rounded-full">
          Open Live App
        </a>
        <Link href={extensionHref} className="px-6 py-3 border border-[var(--color-border)] rounded-full">
          Get Extension
        </Link>
      </div>
    </section>
  );
}
