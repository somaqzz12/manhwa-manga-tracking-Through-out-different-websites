import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-inter",
});

export const metadata: Metadata = {
  title: "Manga Watchlist — Track every chapter",
  description:
    "Manga Watchlist is a manga and manhwa tracker. Sign in from anywhere, build your watchlist, and use the Chrome extension to sync the chapter you read. Unread counts and one-click Continue.",
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
    <html lang="en" className={inter.variable}>
      <body className={`${inter.className} bg-grid-fade bg-background`}>
        {children}
      </body>
    </html>
  );
}
