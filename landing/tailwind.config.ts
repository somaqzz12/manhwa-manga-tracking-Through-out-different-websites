import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        background: "var(--color-background)",
        card: "var(--color-surface)",
        text: "var(--color-text)",
        muted: "var(--color-muted)",
        accent: "var(--color-accent)",
        border: "var(--color-border)",
      },
      fontFamily: {
        sans: ["var(--font-inter)", "system-ui", "sans-serif"],
        serif: ["var(--font-display)", "Georgia", "serif"],
      },
      backgroundImage: {
        "grid-fade":
          "radial-gradient(ellipse 920px 540px at 94% -8%, rgba(124, 92, 255, 0.16), transparent 56%), radial-gradient(ellipse 620px 380px at 8% 100%, rgba(167, 139, 250, 0.09), transparent 52%)",
      },
      boxShadow: {
        accent: "0 10px 28px rgba(124, 92, 255, 0.22)",
        accentLg: "0 24px 54px rgba(124, 92, 255, 0.16)",
      },
    },
  },
  plugins: [],
};

export default config;
