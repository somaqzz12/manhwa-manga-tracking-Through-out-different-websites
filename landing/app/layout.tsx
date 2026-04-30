import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Manga Watchlist — Search, compare, track",
  description:
    "Search any manga or manhwa. Find the best source. Track updates beautifully. Paste any URL, compare sites, and keep one library — with an optional Chrome companion for chapter detection.",
  metadataBase: new URL("https://mangawatchlist.space"),
  openGraph: {
    title: "Manga Watchlist",
    description:
      "Manga & manhwa watchlist. Sign in anywhere — dashboard plus Chrome extension keep every chapter in sync.",
    type: "website",
    url: "https://mangawatchlist.space",
  },
  verification: {
    google: "MDvTaEaXcUEc4wPBYIvZpWAgwXVuK12chNDMNF-eUbc",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Playfair+Display:wght@600;700&display=swap"
          rel="stylesheet"
        />
      </head>
      <body className="bg-background">{children}</body>
    </html>
  );
}
