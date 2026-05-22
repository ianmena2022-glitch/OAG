/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ['./src/renderer/**/*.{js,ts,jsx,tsx,html}'],
  theme: {
    extend: {
      colors: {
        oag: {
          dark: '#1C2B3A',
          blue: '#1A4A8A',
          light: '#F5F6F8',
          border: '#DDE1E7',
          text: '#1A1A2E',
          muted: '#6B7280',
          zebra: '#F0F4F8',
          success: '#2D7A4F',
          error: '#C0392B',
          warning: '#D97706',
          accent: '#2D5BE3',
        },
      },
      fontFamily: {
        sans: ['Inter', 'Calibri', 'system-ui', 'sans-serif'],
      },
    },
  },
  plugins: [],
}
