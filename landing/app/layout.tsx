import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-inter",
});

export const metadata: Metadata = {
  title: "Zero Hour — Hit zero on every series",
  description:
    "Zero Hour is a manga and manhwa tracker. Sign in from anywhere, build your library, and use the Chrome extension to sync the chapter you read. Unread counts and one-click Continue.",
  openGraph: {
    title: "Zero Hour",
    description:
      "Manga & manhwa tracker. Hit zero unread on every series — dashboard plus Chrome extension keep your account in sync.",
    type: "website",
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
