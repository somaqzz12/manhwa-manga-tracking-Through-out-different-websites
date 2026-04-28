import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        background: "#030712",
        card: "#111827",
      },
      fontFamily: {
        sans: ["var(--font-inter)", "system-ui", "sans-serif"],
      },
      backgroundImage: {
        "grid-fade":
          "radial-gradient(ellipse 900px 520px at 92% -8%, rgba(99, 102, 241, 0.12), transparent 55%), radial-gradient(ellipse 600px 400px at 100% 12%, rgba(56, 189, 248, 0.05), transparent 50%)",
      },
      boxShadow: {
        accent: "0 8px 32px rgba(99, 102, 241, 0.25)",
        accentLg: "0 24px 64px rgba(99, 102, 241, 0.15)",
      },
    },
  },
  plugins: [],
};

export default config;
