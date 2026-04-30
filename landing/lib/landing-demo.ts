/** Static demo data for the marketing homepage — labeled “Featured examples” in UI. */

export type DemoSeriesCard = {
  slug: string;
  title: string;
  typeLabel: "Manga" | "Manhwa";
  latestChapter: string;
  sourcesFound: number;
};

export const demoTrendingWeek: DemoSeriesCard[] = [
  { slug: "solo-leveling", title: "Solo Leveling", typeLabel: "Manhwa", latestChapter: "179", sourcesFound: 4 },
  { slug: "omniscient-reader", title: "Omniscient Reader", typeLabel: "Manhwa", latestChapter: "257", sourcesFound: 0 },
  { slug: "tower-of-god", title: "Tower of God", typeLabel: "Manhwa", latestChapter: "640", sourcesFound: 0 },
  {
    slug: "the-beginning-after-the-end",
    title: "The Beginning After the End",
    typeLabel: "Manhwa",
    latestChapter: "204",
    sourcesFound: 0,
  },
  { slug: "jujutsu-kaisen", title: "Jujutsu Kaisen", typeLabel: "Manga", latestChapter: "271", sourcesFound: 0 },
  { slug: "one-piece", title: "One Piece", typeLabel: "Manga", latestChapter: "1113", sourcesFound: 0 },
];

export const demoPopularManhwa: DemoSeriesCard[] = [
  { slug: "solo-leveling", title: "Solo Leveling", typeLabel: "Manhwa", latestChapter: "179", sourcesFound: 4 },
  { slug: "tower-of-god", title: "Tower of God", typeLabel: "Manhwa", latestChapter: "640", sourcesFound: 0 },
  { slug: "omniscient-reader", title: "Omniscient Reader", typeLabel: "Manhwa", latestChapter: "257", sourcesFound: 0 },
  {
    slug: "the-beginning-after-the-end",
    title: "The Beginning After the End",
    typeLabel: "Manhwa",
    latestChapter: "204",
    sourcesFound: 0,
  },
  { slug: "lookism", title: "Lookism", typeLabel: "Manhwa", latestChapter: "498", sourcesFound: 0 },
  { slug: "eleceed", title: "Eleceed", typeLabel: "Manhwa", latestChapter: "318", sourcesFound: 0 },
];

export const demoPopularManga: DemoSeriesCard[] = [
  { slug: "one-piece", title: "One Piece", typeLabel: "Manga", latestChapter: "1113", sourcesFound: 0 },
  { slug: "jujutsu-kaisen", title: "Jujutsu Kaisen", typeLabel: "Manga", latestChapter: "271", sourcesFound: 0 },
  { slug: "chainsaw-man", title: "Chainsaw Man", typeLabel: "Manga", latestChapter: "196", sourcesFound: 0 },
  { slug: "blue-lock", title: "Blue Lock", typeLabel: "Manga", latestChapter: "300", sourcesFound: 0 },
  { slug: "vinland-saga", title: "Vinland Saga", typeLabel: "Manga", latestChapter: "220", sourcesFound: 0 },
  { slug: "berserk", title: "Berserk", typeLabel: "Manga", latestChapter: "378", sourcesFound: 0 },
];

export const demoRecentRows: { title: string; source: string; chapter: string; status: string }[] = [
  { title: "Solo Leveling", source: "MangaDex", chapter: "Ch. 200", status: "Featured example" },
  { title: "Jujutsu Kaisen", source: "Manga Plus", chapter: "Ch. 271", status: "Featured example" },
  { title: "Tower of God", source: "WEBTOON", chapter: "Ch. 640", status: "Featured example" },
  { title: "Omniscient Reader", source: "Manual", chapter: "Ch. 257", status: "Featured example" },
  { title: "Chainsaw Man", source: "MangaDex", chapter: "Ch. 196", status: "Featured example" },
];
