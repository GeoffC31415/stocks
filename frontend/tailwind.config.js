/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        aurora: {
          base: "rgb(var(--bg-base-rgb) / <alpha-value>)",
          surface: "rgb(var(--bg-surface-rgb) / <alpha-value>)",
          glass: "rgb(var(--bg-surface-rgb) / <alpha-value>)",
          violet: "#818cf8",
          cyan: "#38bdf8",
          indigo: "#6366f1",
          rose: "#fb7185"
        },
        pos: "#34d399",
        neg: "#fb7185",
        slate: {
          400: "#94a3b8",
          500: "#7c8ba1",
          600: "#64748b",
          925: "#0b0f17"
        }
      },
      fontFamily: {
        display: [
          "Inter",
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "Roboto",
          "Arial",
          "sans-serif"
        ]
      },
      keyframes: {
        "fade-in": {
          from: { opacity: "0", transform: "translateY(4px)" },
          to: { opacity: "1", transform: "translateY(0)" }
        }
      },
      animation: {
        "fade-in": "fade-in 220ms ease-out"
      },
      boxShadow: {
        "glow-pos": "0 1px 0 0 rgba(52, 211, 153, 0.16) inset",
        "glow-neg": "0 1px 0 0 rgba(251, 113, 133, 0.16) inset",
        "glow-accent":
          "0 1px 0 0 rgba(255, 255, 255, 0.14) inset, 0 8px 20px -12px rgba(14, 165, 233, 0.45)",
        glass:
          "0 1px 0 0 rgba(255, 255, 255, 0.04) inset, 0 12px 32px -18px rgba(0, 0, 0, 0.75)"
      },
      backgroundImage: {
        "aurora-accent":
          "linear-gradient(180deg, #0ea5e9 0%, #0284c7 100%)",
        "aurora-accent-soft":
          "linear-gradient(180deg, rgba(56, 189, 248, 0.14) 0%, rgba(56, 189, 248, 0.06) 100%)"
      }
    }
  },
  plugins: []
};
