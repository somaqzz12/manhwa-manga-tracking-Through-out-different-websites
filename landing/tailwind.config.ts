import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        background: "var(--color-background)",
        card: "var(--color-surface)",
        surface2: "var(--color-surface-2)",
        text: "var(--color-text)",
        muted: "var(--color-muted)",
        accent: "var(--color-accent)",
        accent2: "var(--color-accent-2)",
        border: "var(--color-border)",
      },
      fontFamily: {
        sans: ["var(--font-inter)", "system-ui", "sans-serif"],
        serif: ["var(--font-display)", "Georgia", "serif"],
      },
      backgroundImage: {
        "grid-fade":
          "radial-gradient(ellipse 920px 540px at 94% -8%, color-mix(in srgb, var(--color-accent) 12%, transparent), transparent 56%), radial-gradient(ellipse 620px 380px at 8% 100%, color-mix(in srgb, var(--color-accent-2) 10%, transparent), transparent 52%)",
      },
      boxShadow: {
        accent: "0 10px 28px color-mix(in srgb, var(--color-accent) 22%, transparent)",
        accentLg: "0 24px 54px color-mix(in srgb, var(--color-accent) 16%, transparent)",
      },
    },
  },
  plugins: [],
};

export default config;
