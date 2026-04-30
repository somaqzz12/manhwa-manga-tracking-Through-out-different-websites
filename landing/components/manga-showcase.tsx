import type { DemoSeriesCard } from "@/lib/landing-demo";
import { dashboardUrl } from "@/lib/site-config";

/** Editorial abstract gradients per slug — no panel art, safe placeholders. */
const SLUG_COVER_BG: Record<string, string> = {
  "solo-leveling": "linear-gradient(155deg, #12151c 0%, #283652 42%, #5f7dae 100%)",
  "omniscient-reader": "linear-gradient(145deg, #1a2528 0%, #2d4a4f 50%, #7dafb5 100%)",
  "tower-of-god": "linear-gradient(160deg, #241a10 0%, #5c3d20 45%, #c9a227 100%)",
  "the-beginning-after-the-end": "linear-gradient(150deg, #1c1530 0%, #3d2d5c 50%, #6b8cc4 100%)",
  "jujutsu-kaisen": "linear-gradient(145deg, #1a0a0c 0%, #4a1518 42%, #c94c54 100%)",
  "one-piece": "linear-gradient(155deg, #0c1e2d 0%, #1a4a6e 45%, #3d9bc4 100%)",
  lookism: "linear-gradient(145deg, #222018 0%, #454038 50%, #8a8070 100%)",
  eleceed: "linear-gradient(150deg, #151828 0%, #2a3560 48%, #6b8cff 100%)",
  "chainsaw-man": "linear-gradient(145deg, #1f0c0c 0%, #5c1810 45%, #e85d3a 100%)",
  "blue-lock": "linear-gradient(155deg, #0f2418 0%, #1e5c3a 50%, #7cdf9a 100%)",
  "vinland-saga": "linear-gradient(160deg, #1a2228 0%, #3d4f5c 50%, #8fa9b8 100%)",
  berserk: "linear-gradient(145deg, #120808 0%, #301010 40%, #6b3030 100%)",
};

const FALLBACK_BG =
  "linear-gradient(145deg, color-mix(in srgb, var(--color-accent) 18%, var(--color-surface-2)), var(--color-surface-2))";

function SeriesCard({ card }: { card: DemoSeriesCard }) {
  const base = dashboardUrl.replace(/\/$/, "");
  const discoverQ = `${base}/discover?q=${encodeURIComponent(card.title)}`;
  const addTitle = `${base}/app/add?title=${encodeURIComponent(card.title)}`;
  const bg = SLUG_COVER_BG[card.slug] ?? FALLBACK_BG;

  return (
    <article className="flex h-full min-h-0 flex-col overflow-hidden rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface-2)] shadow-sm">
      <a
        href={discoverQ}
        className="group relative block aspect-[2/3] w-full overflow-hidden"
        aria-hidden="true"
        tabIndex={-1}
      >
        <span
          className="absolute inset-0 transition duration-300 group-hover:scale-[1.03] motion-reduce:transform-none"
          style={{ background: bg, zIndex: 0 }}
          aria-hidden
        />
        {card.coverUrl ? (
          <img
            src={card.coverUrl}
            alt=""
            className="absolute inset-0 z-[1] h-full w-full object-cover"
            loading="lazy"
            decoding="async"
            referrerPolicy="origin"
            onError={(e) => {
              e.currentTarget.remove();
            }}
          />
        ) : null}
      </a>
      <div className="flex flex-1 flex-col gap-1.5 p-3">
        <h3 className="font-sans text-sm font-bold leading-snug text-[var(--color-text)]">{card.title}</h3>
        <p className="text-[0.78rem] leading-snug text-[var(--color-muted)]">
          {card.typeLabel} · Latest ch. {card.latestChapter} · {card.sourcesFound} sources
        </p>
        <div className="mt-auto flex flex-wrap gap-1.5 pt-2">
          <a
            href={discoverQ}
            className="rounded-full border border-[var(--color-border)] bg-[var(--color-surface)] px-2.5 py-1.5 text-[0.72rem] font-semibold text-[var(--color-text)] no-underline transition hover:border-[var(--color-accent)] hover:text-[var(--color-accent)]"
          >
            View sources
          </a>
          <a
            href={addTitle}
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
