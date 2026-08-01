/**
 * Tailwind CSS v4 is a PostCSS plugin and needs no `tailwind.config.js`.
 * Design tokens live in `src/app/globals.css` under `@theme`, which keeps the
 * source of truth for the visual language in CSS rather than split across a JS
 * config and a stylesheet.
 */
const config = {
  plugins: {
    "@tailwindcss/postcss": {},
  },
};

export default config;
