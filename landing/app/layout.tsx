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
    "Manga & manhwa tracker: sign in from anywhere, build your library, and use the Chrome extension to sync the chapter you read. Unread counts and one-click Continue.",
  openGraph: {
    title: "Manga Tracker",
    description:
      "Sign in anywhere. Track series across every site — dashboard and extension keep your account in sync.",
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
