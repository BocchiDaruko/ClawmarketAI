/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      fontFamily: {
        display: ["'Space Mono'", "monospace"],
        body:    ["'DM Sans'", "sans-serif"],
        mono:    ["'JetBrains Mono'", "monospace"],
      },
      colors: {
        claw: {
          bg:      "#080C0F",
          surface: "#0E1419",
          border:  "#1A2332",
          accent:  "#00E5FF",
          green:   "#00FF94",
          amber:   "#FFB800",
          red:     "#FF4560",
          muted:   "#4A6070",
          text:    "#C8D8E4",
        },
      },
      animation: {
        "pulse-slow":  "pulse 3s cubic-bezier(0.4,0,0.6,1) infinite",
        "fade-in":     "fadeIn 0.4s ease forwards",
        "slide-up":    "slideUp 0.4s ease forwards",
        "blink":       "blink 1.2s step-end infinite",
      },
      keyframes: {
        fadeIn:  { from: { opacity: 0 }, to: { opacity: 1 } },
        slideUp: { from: { opacity: 0, transform: "translateY(12px)" }, to: { opacity: 1, transform: "translateY(0)" } },
        blink:   { "0%,100%": { opacity: 1 }, "50%": { opacity: 0 } },
      },
    },
  },
  plugins: [],
};
