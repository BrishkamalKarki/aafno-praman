import type { Metadata, Viewport } from "next";

import "./globals.css";

import { Providers } from "@/components/providers";

export const metadata: Metadata = {
  title: {
    default: "Aafno Praman — verified credentials for Nepal",
    template: "%s · Aafno Praman",
  },
  description:
    "Blockchain-anchored academic and employment credential verification. Issuers publish with consent; anyone can verify in seconds.",
  // The public verify and passport pages are meant to be found. Dashboards
  // opt out individually — a citizen's passport must never be indexed.
  robots: { index: true, follow: true },
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f8fafc" },
    { media: "(prefers-color-scheme: dark)", color: "#0b1120" },
  ],
  // No maximumScale or userScalable:false. Pinch-zoom is how people with low
  // vision read a phone, and disabling it to stop iOS input zoom trades a real
  // accessibility failure for a cosmetic one.
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className="min-h-dvh antialiased">
        {/* First tab stop on every page. Without it, keyboard users traverse
            the whole header on each navigation to reach the content. */}
        <a
          href="#main"
          className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-[var(--radius-control)] focus:bg-surface focus:px-4 focus:py-2 focus:shadow-[var(--shadow-raised)]"
        >
          Skip to content
        </a>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
