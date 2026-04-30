import type { DemoSeriesCard } from "@/lib/landing-demo";
import { dashboardUrl } from "@/lib/site-config";

function SeriesCard({ card }: { card: DemoSeriesCard }) {
  const base = dashboardUrl.replace(/\/$/, "");
  const initial = card.title.charAt(0).toUpperCase() || "?";
  return (
    <article className="flex h-full min-h-0 flex-col overflow-hidden rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface-2)] shadow-sm">
      <a
        href={`${base}/series/${encodeURIComponent(card.slug)}`}
        className="relative block aspect-[2/3] w-full bg-gradient-to-br from-[color-mix(in_srgb,var(--color-accent)_14%,var(--color-surface-2))] to-[var(--color-surface-2)]"
        aria-hidden="true"
        tabIndex={-1}
      >
        <span className="absolute inset-0 grid place-items-center font-serif text-3xl font-bold text-[var(--color-accent)]">
          {initial}
        </span>
      </a>
      <div className="flex flex-1 flex-col gap-1.5 p-3">
        <h3 className="font-sans text-sm font-bold leading-snug text-[var(--color-text)]">{card.title}</h3>
        <p className="text-[0.78rem] leading-snug text-[var(--color-muted)]">
          {card.typeLabel} · Latest ch. {card.latestChapter} · {card.sourcesFound} sources
        </p>
        <div className="mt-auto flex flex-wrap gap-1.5 pt-2">
          <a
            href={`${base}/series/${encodeURIComponent(card.slug)}`}
            className="rounded-full border border-[var(--color-border)] bg-[var(--color-surface)] px-2.5 py-1.5 text-[0.72rem] font-semibold text-[var(--color-text)] no-underline transition hover:border-[var(--color-accent)] hover:text-[var(--color-accent)]"
          >
            View sources
          </a>
          <a
            href={`${base}/discover?q=${encodeURIComponent(card.title)}`}
            className="rounded-full bg-[var(--color-accent)] px-2.5 py-1.5 text-[0.72rem] font-semibold text-[#fffaf3] no-underline transition hover:brightness-105"
          >
            Add
          </a>
        </div>
      </div>
    </article>
  );
}

export function MangaShowcaseSection({
  kicker,
  title,
  subtitle,
  cards,
  columns = "responsive",
}: {
  kicker: string;
  title: string;
  subtitle?: string;
  cards: DemoSeriesCard[];
  columns?: "responsive" | "dense";
}) {
  const grid =
    columns === "dense"
      ? "grid gap-4 grid-cols-2 sm:grid-cols-3 lg:grid-cols-6"
      : "grid gap-4 grid-cols-2 sm:grid-cols-3 lg:grid-cols-3";

  return (
    <section className="border-t border-[var(--color-border)] px-4 py-14 sm:px-8 md:px-12">
      <div className="mx-auto max-w-6xl">
        <p className="mb-2 text-xs font-bold uppercase tracking-wider text-[var(--color-muted)]">{kicker}</p>
        <h2 className="font-serif text-2xl font-bold text-[var(--color-text)] sm:text-3xl">{title}</h2>
        {subtitle ? <p className="mt-2 max-w-2xl text-[var(--color-muted)]">{subtitle}</p> : null}
        <div className={`${grid} mt-8 auto-rows-fr`}>
          {cards.map((c) => (
            <SeriesCard key={c.slug} card={c} />
          ))}
        </div>
      </div>
    </section>
  );
}
