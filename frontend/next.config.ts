import type { NextConfig } from "next";

/**
 * Security headers are set here rather than in a proxy so they travel with the
 * app across every target the deployment plan names — Vercel, Render, Docker.
 * A header configured only in one platform's dashboard is a header that
 * silently disappears the first time the app is deployed anywhere else.
 *
 * No Content-Security-Policy yet: a CSP that is wrong is worse than none,
 * because the usual response to a broken page is to weaken it to
 * `unsafe-inline` and leave it there. It lands with the frontend's script
 * inventory settled, not before.
 */
const securityHeaders = [
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  {
    // The app needs no camera or microphone. A QR scanner on the verifier
    // screen will need `camera=(self)` — change it deliberately, then.
    key: "Permissions-Policy",
    value: "camera=(), microphone=(), geolocation=(), payment=()",
  },
];

const nextConfig: NextConfig = {
  reactStrictMode: true,

  typescript: {
    // Never ship with type errors suppressed. This is the default; it is
    // written out so nobody "temporarily" flips it during a demo crunch.
    ignoreBuildErrors: false,
  },

  // Next 16 removed `eslint` from NextConfig — linting no longer runs as part
  // of `next build`. It is a separate CI step (`npm run lint`) instead, which
  // is the better arrangement anyway: a lint warning should not be able to fail
  // a deploy, and a type error still should.

  async headers() {
    return [{ source: "/:path*", headers: securityHeaders }];
  },
};

export default nextConfig;
