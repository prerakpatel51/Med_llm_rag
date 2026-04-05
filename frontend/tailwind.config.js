/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        // Trust tier colors used on citation badges
        "tier-a": "#16a34a",  // green-600
        "tier-b": "#d97706",  // amber-600
        "tier-c": "#dc2626",  // red-600
      },
    },
  },
  plugins: [],
};
