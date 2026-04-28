import { BookOpen, Cpu, Link2, Puzzle } from "lucide-react";

const steps = [
  {
    n: "01",
    icon: Cpu,
    title: "Host the server",
    text: "Run the Flask app (SQLite locally or Postgres on Render). HTTPS in production unlocks extension sync.",
  },
  {
    n: "02",
    icon: Link2,
    title: "Add series URLs",
    text: "Paste each series listing URL; the tracker scrapes cover art and discovers the newest chapter slot on schedule.",
  },
  {
    n: "03",
    icon: Puzzle,
    title: "Install the companion",
    text: "Load the Chromium extension from the Web Store or your build, paste your API base URL, and stay Connected.",
  },
  {
    n: "04",
    icon: BookOpen,
    title: "Just read",
    text: "On chapter pages the extension parses the chapter, updates last-seen per title, keeps unread badges truthful, and the dashboard mirrors it all.",
  },
] as const;

export function HowItWorks() {
  return (
    <section className="border-t border-white/[0.06] bg-gradient-to-b from-transparent to-black/20 px-4 py-20 sm:px-6">
      <div className="mx-auto max-w-6xl">
        <div className="mx-auto max-w-2xl text-center">
          <h2 className="text-3xl font-bold tracking-tight text-white sm:text-4xl">
            How it works
          </h2>
          <p className="mt-4 text-lg text-slate-400">
            Scraping stays on your server — the extension&apos;s role is detecting the
            page you&apos;re reading and syncing that single fact back.
          </p>
        </div>

        <ol className="mt-16 grid gap-10 lg:grid-cols-4 lg:gap-6">
          {steps.map(({ n, icon: Icon, title, text }) => (
            <li
              key={n}
              className="relative flex flex-col rounded-2xl border border-white/[0.07] bg-card p-6 ring-1 ring-white/[0.03]"
            >
              <span className="mb-4 font-mono text-xs font-semibold uppercase tracking-[0.2em] text-indigo-400/90">
                {n}
              </span>
              <div className="mb-4 inline-flex size-10 items-center justify-center rounded-xl bg-indigo-500/12 text-indigo-300">
                <Icon className="h-5 w-5" strokeWidth={1.75} aria-hidden />
              </div>
              <h3 className="text-lg font-semibold text-white">{title}</h3>
              <p className="mt-2 flex-1 text-sm leading-relaxed text-slate-400">
                {text}
              </p>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}
