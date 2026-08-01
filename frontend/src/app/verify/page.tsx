"use client";

import { useState } from "react";
import Link from "next/link";

import { Logo } from "@/components/brand/logo";
import { Button } from "@/components/ui/button";
import { Card, CardBody } from "@/components/ui/card";
import { FormError, inputClass, labelClass } from "@/components/ui/form";
import { TxLink } from "@/components/ui/tx-link";
import { OutcomePanel } from "@/components/verification/outcome-panel";
import { apiFetch } from "@/lib/api/client";
import { errorMessage } from "@/lib/api/errors";
import { anchorLabel, formatDate, recordTitle, type CredentialRecord } from "@/lib/api/types";
import { parseOutcome } from "@/lib/verification";

/**
 * Public verification, no account required.
 *
 * The counterpart to `/employer/verify`: that one takes a document, this one
 * takes a reference — a record id or the 64-character hash a QR code carries.
 * Both were reachable from the backend and neither had a page here, so a QR
 * printed on a certificate pointed at nothing.
 *
 * Anonymous callers are rate-limited rather than metered, which is what keeps a
 * candidate sharing their own link from silently burning a recruiter's monthly
 * allowance.
 */

interface LookupResponse {
  result: string;
  reason: string;
  record: CredentialRecord | null;
  issuer: Record<string, unknown>;
  chain: { tx_hash?: string; block_number?: number; chain_id?: number };
  integrity: { expected_hash: string; computed_hash: string; matches: boolean };
}

export default function PublicVerifyPage() {
  const [reference, setReference] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<LookupResponse | null>(null);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setResult(null);

    try {
      setResult(
        await apiFetch<LookupResponse>("/verify/lookup/", {
          method: "POST",
          body: { reference: reference.trim() },
          anonymous: true,
        }),
      );
    } catch (caught) {
      // A NOT_FOUND comes back as 404 with a full outcome body, so it is a
      // result rather than an error — anything reaching here is a real failure.
      setError(errorMessage(caught, "Could not check that reference."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main id="main" className="mx-auto w-full max-w-2xl px-5 py-10 sm:py-14">
      <Logo className="text-sm text-brand" size={22} />
      <h1 className="mt-2 text-2xl font-semibold tracking-tight">Check a credential</h1>
      <p className="mt-1.5 text-sm text-text-muted">
        Paste the reference from a QR code or a certificate. No account needed, and nothing is
        revealed about anyone whose reference you do not already hold.
      </p>

      <Card className="mt-6">
        <CardBody className="pt-5">
          <form onSubmit={submit} className="space-y-4">
            <FormError message={error} />
            <div>
              <label htmlFor="reference" className={labelClass}>
                Record id or fingerprint
              </label>
              <input
                id="reference"
                required
                autoFocus
                value={reference}
                onChange={(event) => setReference(event.target.value)}
                placeholder="e.g. bae1699f-12f9-4221-8731-440289be686a"
                className={`${inputClass} font-mono`}
                autoComplete="off"
              />
            </div>
            <Button type="submit" size="lg" loading={busy} disabled={!reference.trim()}>
              Check it
            </Button>
          </form>
        </CardBody>
      </Card>

      {result && (
        <div className="mt-6">
          <OutcomePanel outcome={parseOutcome(result.result)} detail={result.reason}>
            {result.record && (
              <div className="text-sm">
                <p className="font-medium text-text">{recordTitle(result.record)}</p>
                <p className="mt-0.5 text-text-muted">
                  Issued to {result.record.subject_full_name} by {result.record.issuer_name}
                  {result.record.issued_at && ` · ${formatDate(result.record.issued_at)}`}
                </p>
                <p className="mt-1 text-text-muted">{anchorLabel(result.record)}</p>
              </div>
            )}

            <div className="mt-4 border-t border-border pt-3 text-xs text-text-subtle">
              {result.integrity.expected_hash && (
                <p className="break-all">
                  <span className="font-medium text-text-muted">Fingerprint:</span>{" "}
                  <span className="font-mono">{result.integrity.expected_hash}</span>{" "}
                  {result.integrity.matches
                    ? "· recomputed and matches"
                    : "· does NOT match the recomputed value"}
                </p>
              )}
              {result.chain?.tx_hash && (
                <p className="mt-1 break-all">
                  <span className="font-medium text-text-muted">Anchored in:</span>{" "}
                  <TxLink hash={result.chain.tx_hash} />
                  {result.chain.block_number ? ` · block ${result.chain.block_number}` : ""}
                </p>
              )}
            </div>
          </OutcomePanel>
        </div>
      )}

      <p className="mt-8 text-center text-sm text-text-muted">
        Have the certificate itself rather than a reference?{" "}
        <Link href="/employer/verify" className="font-medium text-brand hover:underline">
          Upload it instead
        </Link>
      </p>
    </main>
  );
}
