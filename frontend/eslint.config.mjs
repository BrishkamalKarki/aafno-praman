import next from "eslint-config-next";

/**
 * ESLint flat config.
 *
 * `npm run lint` was declared in package.json but had no config file to read, so
 * it had never actually run. eslint-config-next 16 exports a flat config array
 * directly, so no `FlatCompat` bridge is needed (and the bridge in fact fails on
 * this version — it tries to JSON-stringify a plugin graph that is circular).
 *
 * Linting is a separate step and deliberately not part of `next build`: a style
 * warning should not be able to fail a deploy, while a type error still should.
 */
const config = [
  {
    ignores: [
      ".next/**",
      "node_modules/**",
      "next-env.d.ts",
      // Generated from the backend's OpenAPI document. Regenerate it with
      // `npm run api:types`; there is nothing useful to lint in it.
      "src/lib/api/schema.d.ts",
    ],
  },
  ...next,
];

export default config;
