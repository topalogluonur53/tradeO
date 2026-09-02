import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        background: "#0b0f14",
        panel: "#121922",
        panelMuted: "#182231",
        line: "#263241",
        textPrimary: "#f3f7fb",
        textMuted: "#94a3b8",
        accent: "#2dd4bf",
        amber: "#f59e0b",
        danger: "#f43f5e"
      },
      boxShadow: {
        terminal: "0 18px 60px rgba(0, 0, 0, 0.35)"
      }
    }
  },
  plugins: []
};

export default config;
