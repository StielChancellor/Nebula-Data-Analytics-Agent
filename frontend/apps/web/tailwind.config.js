/**
 * Tailwind config — consumes brand-runtime CSS vars via rgb(var(--accent) / <alpha-value>).
 * The Aurora default theme lives in src/index.css; brand-runtime overrides
 * --accent at runtime.
 */
/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{ts,tsx}",
    "../../packages/**/src/**/*.{ts,tsx}",
  ],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        accent: "rgb(var(--accent) / <alpha-value>)",
        "accent-glow": "rgb(var(--accent-glow) / <alpha-value>)",
        "accent-soft": "rgb(var(--accent-soft) / <alpha-value>)",
        "accent-foreground": "rgb(var(--accent-foreground) / <alpha-value>)",
        // Aurora deep-space neutrals
        ink: {
          50:  "#f4f6fa",
          100: "#dbe1ee",
          200: "#a5b0c8",
          300: "#6f7c9c",
          400: "#3f4a66",
          500: "#222b45",
          600: "#171e33",
          700: "#0f1626",
          800: "#0a101c",
          900: "#060912",
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'Segoe UI', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'SFMono-Regular', 'monospace'],
      },
      borderRadius: {
        DEFAULT: "0.5rem",
      },
    },
  },
  plugins: [],
};
