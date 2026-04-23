/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ['./src/**/*.{js,jsx,ts,tsx}', './public/index.html'],
  theme: {
    extend: {
      colors: {
        navy: {
          DEFAULT: '#1e3a5f',
          dark: '#16283f',
          deep: '#0f2340',
          soft: '#2a4a75',
        },
        gold: {
          DEFAULT: '#d4a84b',
          light: '#e0bc68',
          dark: '#b8902f',
        },
        terracotta: {
          DEFAULT: '#b85c38',
          light: '#cc7857',
          dark: '#8f4527',
        },
        ink: '#111827',
        muted: '#6b7280',
        hairline: '#e5e7eb',
        paper: '#ffffff',
        mist: '#f7f8fa',
      },
      fontFamily: {
        serif: ['"Playfair Display"', 'Georgia', 'serif'],
        sans: ['Inter', 'ui-sans-serif', 'system-ui', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'Roboto', 'Helvetica Neue', 'Arial', 'sans-serif'],
      },
      maxWidth: {
        content: '1160px',
      },
      letterSpacing: {
        wider2: '0.12em',
      },
    },
  },
  plugins: [],
};
