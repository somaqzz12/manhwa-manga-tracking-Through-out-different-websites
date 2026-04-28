import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-inter",
});

export const metadata: Metadata = {
  title: "Manga Tracker — Never lose your place",
  description:
    "Self-hosted manga & manhwa tracker with a Chrome extension that syncs the chapter you are reading. Library, unread counts, and one-click continue.",
  openGraph: {
    title: "Manga Tracker",
    description:
      "Track series across every site. Dashboard + browser extension that keeps progress in sync.",
    type: "website",
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
