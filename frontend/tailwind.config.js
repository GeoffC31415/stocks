/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        aurora: {
          base: "#070a1a",
          surface: "#0d1224",
          glass: "rgba(15, 23, 42, 0.55)",
          violet: "#a78bfa",
          cyan: "#22d3ee",
          indigo: "#6366f1",
          rose: "#fb7185"
        },
        pos: "#34d399",
        neg: "#f87171",
        slate: {
          925: "#0b1222"
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
        "aurora-drift": {
          "0%, 100%": {
            transform: "translate3d(0, 0, 0) scale(1)"
          },
          "33%": {
            transform: "translate3d(4%, -3%, 0) scale(1.08)"
          },
          "66%": {
            transform: "translate3d(-3%, 2%, 0) scale(0.94)"
          }
        },
        "aurora-drift-slow": {
          "0%, 100%": {
            transform: "translate3d(0, 0, 0) scale(1)"
          },
          "50%": {
            transform: "translate3d(-5%, 4%, 0) scale(1.12)"
          }
        },
        "glow-pulse": {
          "0%, 100%": { opacity: "0.55" },
          "50%": { opacity: "0.85" }
        },
        "fade-in": {
          from: { opacity: "0", transform: "translateY(6px)" },
          to: { opacity: "1", transform: "translateY(0)" }
        }
      },
      animation: {
        "aurora-drift": "aurora-drift 28s ease-in-out infinite",
        "aurora-drift-slow": "aurora-drift-slow 42s ease-in-out infinite",
        "glow-pulse": "glow-pulse 6s ease-in-out infinite",
        "fade-in": "fade-in 280ms ease-out"
      },
      boxShadow: {
        "glow-pos": "0 0 24px rgba(52, 211, 153, 0.28)",
        "glow-neg": "0 0 24px rgba(248, 113, 113, 0.28)",
        "glow-accent":
          "0 0 28px rgba(167, 139, 250, 0.25), 0 0 48px rgba(34, 211, 238, 0.18)",
        glass:
          "0 1px 0 0 rgba(255,255,255,0.04) inset, 0 24px 60px -28px rgba(8, 12, 30, 0.7)"
      },
      backgroundImage: {
        "aurora-accent":
          "linear-gradient(135deg, #a78bfa 0%, #22d3ee 100%)",
        "aurora-accent-soft":
          "linear-gradient(135deg, rgba(167,139,250,0.18) 0%, rgba(34,211,238,0.18) 100%)"
      }
    }
  },
  plugins: []
};
