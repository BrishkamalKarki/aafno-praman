"use client";

import { QuotaMeter } from "@/components/employer/quota-meter";
import { useQuota } from "@/lib/api/hooks";
import { planIdFor } from "@/lib/plans";

import { VerifyForm } from "./verify-form";

/**
 * Check a certificate.
 *
 * The document comes first, and that is a security decision rather than a UX
 * one. The obvious design — type a name and a citizenship number, see if they
 * exist — is a national PII enumeration oracle: Nepali citizenship numbers are
 * district-structured and sequentially issued, so the keyspace can be walked.
 * Possession of the document *is* the authorisation here, and the identity
 * fields below it are an assertion checked against the matched record, never a
 * query. Someone holding no document learns nothing, at any rate limit.
 *
 * The hash is computed server-side because the verdict is not "does this file's
 * hash exist" — a PDF re-saved by a reader or recompressed by a mail gateway has
 * different bytes and an identical meaning. The byte match is only the lookup;
 * the verdict comes from recomputing the canonical payload and checking the
 * ledger.
 */
export default function VerifyPage() {
  const quota = useQuota();

  return (
    <div className="mx-auto w-full max-w-2xl">
      <h1 className="text-lg font-semibold tracking-tight">Check a certificate</h1>
      <p className="mt-1.5 text-sm text-text-muted">
        Upload the document a candidate gave you. We hash it, match it against the ledger, and
        tell you what is actually true about it — including when we cannot confirm who it
        belongs to.
      </p>

      <div className="mt-4">
        <QuotaMeter
          plan={planIdFor(quota.data?.plan)}
          used={quota.data?.used ?? 0}
          limit={quota.data?.limit ?? null}
          {...(quota.data?.resets_at ? { resetsAt: quota.data.resets_at } : {})}
          compact
        />
      </div>

      <VerifyForm />
    </div>
  );
}
