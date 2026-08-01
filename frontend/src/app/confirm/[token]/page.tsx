import type { Metadata } from "next";

import { ConfirmPanel } from "./confirm-panel";

/**
 * The "is this you?" page.
 *
 * Reached from an email link by someone who very likely has no account and has
 * never heard of the platform. Three constraints follow:
 *
 * 1. **No login wall.** The token is the credential. Forcing a signup before
 *    someone can say "no, wrong person" would be absurd.
 * 2. **Nothing happens on load.** The record is read, never answered. Mail
 *    scanners and link prefetchers follow URLs; a page that confirmed on GET
 *    would have credentials accepted by antivirus software rather than people.
 * 3. **Never indexed.** A confirmation URL in a search index is a published
 *    credential offer with someone's name on it.
 */
export const metadata: Metadata = {
  title: "Confirm your credential",
  robots: { index: false, follow: false },
};

export default async function ConfirmPage({
  params,
}: {
  params: Promise<{ token: string }>;
}) {
  const { token } = await params;

  return (
    <main id="main" className="mx-auto w-full max-w-2xl px-5 py-10 sm:py-16">
      <ConfirmPanel token={token} />
    </main>
  );
}
