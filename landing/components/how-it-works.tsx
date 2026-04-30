import { BookOpen, Link2, Puzzle, UserRound } from "lucide-react";

const steps = [
  {
    n: "01",
    icon: UserRound,
    title: "Create your account",
    text: "Register on the web app with a username and password. That login is yours everywhere — same credentials on a new browser or country.",
  },
  {
    n: "02",
    icon: Link2,
    title: "Add series URLs",
    text: "Paste each series listing URL; Manga Watchlist pulls cover art and checks for new chapters on a schedule.",
  },
  {
    n: "03",
    icon: Puzzle,
    title: "Install the companion",
    text: "Add the Chrome extension. It’s pre-pointed at Manga Watchlist, so it just connects once you’re signed in there.",
  },
  {
    n: "04",
    icon: BookOpen,
    title: "Just read",
    text: "On chapter pages the extension reads the chapter, updates your last-seen, keeps unread badges accurate, and the dashboard shows the same data for your user.",
  },
] as const;

export function HowItWorks() {
  return (
    <section className="border-t border-[var(--color-border)] bg-gradient-to-b from-transparent to-[color-mix(in_srgb,var(--color-accent)_7%,transparent)] px-4 py-20 sm:px-6">
      <div className="mx-auto max-w-6xl">
        <div className="mx-auto max-w-2xl text-center">
          <h2 className="font-serif text-3xl font-bold tracking-tight text-[var(--color-text)] sm:text-4xl">
            How it works
          </h2>
          <p className="mt-4 text-lg text-[var(--color-muted)]">
            Library data is stored per user in the app&apos;s database. The extension
            only detects which chapter you opened and sends that to your account.
          </p>
        </div>

        <ol className="mt-16 grid gap-10 lg:grid-cols-4 lg:gap-6">
          {steps.map(({ n, icon: Icon, title, text }) => (
            <li
              key={n}
              className="relative flex flex-col rounded-2xl border border-[var(--color-border)] bg-card p-6 ring-1 ring-black/5"
            >
              <span className="mb-4 font-mono text-xs font-semibold uppercase tracking-[0.2em] text-[var(--color-accent)]">
                {n}
              </span>
              <div className="mb-4 inline-flex size-10 items-center justify-center rounded-xl bg-[var(--color-accent)]/15 text-[var(--color-accent)]">
                <Icon className="h-5 w-5" strokeWidth={1.75} aria-hidden />
              </div>
              <h3 className="font-serif text-lg font-semibold text-[var(--color-text)]">{title}</h3>
              <p className="mt-2 flex-1 text-sm leading-relaxed text-[var(--color-muted)]">
                {text}
              </p>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}
