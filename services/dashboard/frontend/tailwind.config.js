/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        surface: { DEFAULT: "#0f1117", card: "#161a25", hover: "#1c2030" },
        accent: { green: "#22c55e", red: "#ef4444", blue: "#3b82f6", yellow: "#eab308" },
      },
    },
  },
  plugins: [],
}
