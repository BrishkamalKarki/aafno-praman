import type { Metadata } from "next";

import { SharedPassport } from "./shared-passport";

/**
 * The destination of every share link and every QR code.
 *
 * This route did not exist, which made the citizen's entire outward flow a dead
 * end: `ShareLink.url` is built server-side as `${PUBLIC_APP_URL}/s/{token}`,
 * so a link created on `/citizen/shares/new`, copied, and sent to an employer
 * landed on a 404 — as did the QR code rendered from the same URL.
 *
 * No login wall, by design. The recruiter opening this has no account and does
 * not want one; the token is the authorisation, which is exactly why the holder
 * can revoke it, expire it, cap its views and put a passphrase on it.
 *
 * Never indexed. A share link in a search index is a published credential with
 * someone's name attached, and it would outlive the revocation that was
 * supposed to take it back.
 */
export const metadata: Metadata = {
  title: "Shared credentials",
  robots: { index: false, follow: false },
};

export default async function SharedPassportPage({
  params,
}: {
  params: Promise<{ token: string }>;
}) {
  const { token } = await params;

  return (
    <main id="main" className="mx-auto w-full max-w-3xl px-5 py-10 sm:py-14">
      <SharedPassport token={token} />
    </main>
  );
}
