/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{vue,js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        "primary": "#2563eb",
        "primary-hover": "#1d4ed8",
        "bg-main": "#f8fafc",
        "panel": "#ffffff",
        "border-light": "#e2e8f0",
        "text-main": "#1e293b",
        "text-muted": "#64748b",
        "accent-blue": "#eff6ff"
      },
      fontFamily: {
        "sans": ["Inter", "sans-serif"],
        "display": ["Space Grotesk", "sans-serif"]
      },
    },
  },
  plugins: [],
}
