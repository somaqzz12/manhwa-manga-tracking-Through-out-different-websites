import {
  ArrowDownToLine,
  BookMarked,
  Cloud,
  Globe2,
  Puzzle,
  RefreshCw,
} from "lucide-react";

const features = [
  {
    icon: Puzzle,
    title: "Companion extension",
    body: "Reads the chapter URL on manga and manhwa sites, syncs progress to your logged-in account, and shows a live unread badge.",
  },
  {
    icon: RefreshCw,
    title: "Scheduled checks",
    body: "Manga Watchlist checks listing pages on a timer so “latest chapter” and behind counts stay fresh without you refreshing anything.",
  },
  {
    icon: BookMarked,
    title: "One library",
    body: "Track series from many hosts in one dashboard — sort, search, Continue links, and read-through controls per title.",
  },
  {
    icon: Globe2,
    title: "Site profiles + heuristics",
    body: "Built-in parsers for popular readers plus generic fallbacks so new mirrors don’t break your workflow.",
  },
  {
    icon: ArrowDownToLine,
    title: "Portable data",
    body: "Export or import your library as JSON for backups or moving your list to another setup.",
  },
  {
    icon: Cloud,
    title: "Your account, anywhere",
    body: "Your series, chapters, and passwords (stored securely hashed) live in the app’s database — sign in from any device with the same username and password.",
  },
] as const;

export function FeatureGrid() {
  return (
    <section className="border-t border-white/[0.06] px-4 py-20 sm:px-6">
      <div className="mx-auto max-w-6xl">
        <div className="mx-auto max-w-2xl text-center">
          <h2 className="text-3xl font-bold tracking-tight text-white sm:text-4xl">
            Built for heavy readers
          </h2>
          <p className="mt-4 text-lg text-slate-400">
            Everything you need to stay current without spreadsheets or fragile
            bookmarks.
          </p>
        </div>
        <div className="mt-14 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {features.map(({ icon: Icon, title, body }) => (
            <article
              key={title}
              className="group rounded-2xl border border-white/[0.07] bg-card p-6 shadow-sm ring-1 ring-white/[0.03] transition hover:border-indigo-500/30 hover:ring-indigo-500/20"
            >
              <div className="mb-4 inline-flex size-11 items-center justify-center rounded-xl bg-indigo-500/15 text-indigo-300 transition group-hover:bg-indigo-500/25 group-hover:text-indigo-200">
                <Icon className="h-5 w-5" strokeWidth={1.75} aria-hidden />
              </div>
              <h3 className="text-lg font-semibold text-white">{title}</h3>
              <p className="mt-2 text-sm leading-relaxed text-slate-400">{body}</p>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}
