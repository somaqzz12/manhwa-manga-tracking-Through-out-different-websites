import type { NextConfig } from "next";

const basePath =
  process.env.NEXT_PUBLIC_BASE_PATH?.trim() &&
  /^\/[a-zA-Z0-9/_\-]*$/.test(process.env.NEXT_PUBLIC_BASE_PATH!.trim())
    ? process.env.NEXT_PUBLIC_BASE_PATH!.trim()
    : "";

/** Static export friendly for GitHub Pages; omit output for SSR on Vercel if you prefer. */
const config: NextConfig = {
  output: process.env.STATIC_EXPORT === "1" ? "export" : undefined,
  basePath,
  ...(basePath ? { assetPrefix: basePath } : {}),
  images: process.env.STATIC_EXPORT === "1" ? { unoptimized: true } : undefined,
};

export default config;
