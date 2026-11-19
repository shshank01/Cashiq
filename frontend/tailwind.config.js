/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        primary: {
          DEFAULT: '#0D9488', // teal-600
          dark: '#0F766E',    // teal-700
          light: '#14B8A6',   // teal-500
        },
        background: '#FAFAF9', // stone-50
        surface: '#FFFFFF',
        text: {
          primary: '#1C1917',   // stone-900
          secondary: '#57534E', // stone-600
          tertiary: '#A8A29E',  // stone-400
        },
        border: {
          DEFAULT: '#E7E5E4', // stone-200
          light: '#F5F5F4',   // stone-100
        },
        success: '#059669', // emerald-600
        warning: '#D97706', // amber-600
        danger: '#DC2626',  // red-600
        info: '#0D9488',    // teal-600
      },
      fontFamily: {
        sans: ['Inter', 'ui-sans-serif', 'system-ui', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'Roboto', 'Helvetica Neue', 'Arial', 'sans-serif'],
        serif: ['"Times New Roman"', 'Times', 'serif'],
      },
    },
  },
  plugins: [],
}
