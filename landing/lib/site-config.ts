/**
 * Landing page URLs — prefer env for deploy-specific values (Vercel / GitHub Pages).
 */

export const webStoreUrl = (
  process.env.NEXT_PUBLIC_WEB_STORE_URL ?? ""
).trim();

export const githubUrl =
  process.env.NEXT_PUBLIC_GITHUB_URL?.trim() ||
  "https://github.com/somaqzz12/manhwa-manga-tracking-Through-out-different-websites";

export const bugReportUrl =
  process.env.NEXT_PUBLIC_BUG_REPORT_URL?.trim() ||
  "https://github.com/somaqzz12/manhwa-manga-tracking-Through-out-different-websites/issues";

/** Privacy notes for Chrome Web Store (extension disclosure). */
export const extensionPrivacyHref =
  process.env.NEXT_PUBLIC_EXTENSION_PRIVACY_URL?.trim() || "/privacy";

export const authorName =
  process.env.NEXT_PUBLIC_AUTHOR_NAME?.trim() || "Osamah";

/** Public web app URL where users register and sign in. */
export const dashboardUrl =
  process.env.NEXT_PUBLIC_DASHBOARD_URL?.trim() ||
  "https://api.mangawatchlist.space";
