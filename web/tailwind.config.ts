import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        primary: "#F5A524",
        "on-primary": "#000000",
        "primary-container": "#3D2800",
        "on-primary-container": "#FFDFA6",
        surface: "#0E1116",
        "surface-container-low": "#141820",
        "surface-container": "#1A202C",
        "surface-container-high": "#222B3A",
        "on-surface": "#F0F3F8",
        "on-surface-variant": "#9DA8B9",
        outline: "#323E50",
        "status-critical": "#EF4444",
        "status-warning": "#F5A524",
        "status-normal": "#22C55E",
      },
      fontFamily: {
        body: ['"IBM Plex Sans"', "system-ui", "sans-serif"],
        headline: ['"IBM Plex Sans"', "system-ui", "sans-serif"],
        mono: ['"JetBrains Mono"', "ui-monospace", "monospace"],
      },
    },
  },
  plugins: [],
} satisfies Config;
