"use client";

import { useState } from "react";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import { Card, CardBody } from "@/components/ui/card";
import { FileField } from "@/components/ui/form";
import { TxLink } from "@/components/ui/tx-link";
import { OutcomePanel } from "@/components/verification/outcome-panel";
import { ApiError } from "@/lib/api/client";
import { errorMessage } from "@/lib/api/errors";
import { useVerifyDocument } from "@/lib/api/hooks";
import type { DocumentVerifyResult } from "@/lib/api/types";
import { parseOutcome, type VerificationOutcome } from "@/lib/verification";

type VerifyResponse = DocumentVerifyResult;

export function VerifyForm() {
  const verify = useVerifyDocument();

  const [file, setFile] = useState<File | null>(null);
  const [name, setName] = useState("");
  const [nationalId, setNationalId] = useState("");
  const [result, setResult] = useState<VerifyResponse | null>(null);
  const [error, setError] = useState("");
  const [quotaExhausted, setQuotaExhausted] = useState(false);

  const busy = verify.isPending;

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!file) return;

    setError("");
    setQuotaExhausted(false);
    setResult(null);

    try {
      setResult(
        await verify.mutateAsync({
          document: file,
          claimed_name: name,
          claimed_national_id: nationalId,
        }),
      );
    } catch (caught) {
      // The paywall is not a failure, and framing it as one is what makes an
      // employer conclude the tool is broken rather than that they have run out.
      if (caught instanceof ApiError && caught.isQuotaExceeded) {
        setQuotaExhausted(true);
        setError("You have used this month's verification allowance.");
      } else {
        setError(errorMessage(caught, "Verification failed. Please try again."));
      }
    }
  }

  const outcome: VerificationOutcome | null = result ? parseOutcome(result.result) : null;

  return (
    <>
      <Card className="mt-6">
        <CardBody className="pt-5">
          <form onSubmit={submit} className="space-y-5">
            <FileField
              id="document"
              label="Certificate file"
              required
              accept=".pdf,.png,.jpg,.jpeg"
              file={file}
              onSelect={setFile}
              hint="PDF, PNG or JPEG, up to 10 MB. The file is hashed and discarded — we do not keep a copy."
            />

            <fieldset className="space-y-4 border-t border-border pt-4">
              <legend className="sr-only">Who you believe this belongs to</legend>
              <p className="text-sm font-medium">
                Who gave you this?{" "}
                <span className="font-normal text-text-subtle">(optional)</span>
              </p>

              <div className="grid gap-4 sm:grid-cols-2">
                <div>
                  <label htmlFor="claimed-name" className="block text-sm">
                    Full name
                  </label>
                  <input
                    id="claimed-name"
                    value={name}
                    onChange={(event) => setName(event.target.value)}
                    className="mt-1.5 h-11 w-full rounded-[var(--radius-control)] border border-border-strong bg-surface px-3 text-sm"
                    autoComplete="off"
                  />
                </div>
                <div>
                  <label htmlFor="claimed-nid" className="block text-sm">
                    Citizenship number
                  </label>
                  <input
                    id="claimed-nid"
                    value={nationalId}
                    onChange={(event) => setNationalId(event.target.value)}
                    inputMode="numeric"
                    className="mt-1.5 h-11 w-full rounded-[var(--radius-control)] border border-border-strong bg-surface px-3 text-sm"
                    autoComplete="off"
                  />
                </div>
              </div>

              {/* Says plainly that this is a check, not a search. The distinction
                  is the whole reason this cannot be used to enumerate citizens. */}
              <p className="text-xs text-text-subtle">
                These are checked against the certificate you uploaded. They are
                never used to look people up, and nothing is revealed about
                anyone whose document you do not hold.
              </p>
            </fieldset>

            <Button type="submit" size="lg" loading={busy} disabled={!file}>
              Verify certificate
            </Button>
          </form>
        </CardBody>
      </Card>

      {error && (
        <div
          className="mt-4 rounded-[var(--radius-card)] border p-4 text-sm"
          style={{
            color: "var(--color-danger)",
            backgroundColor: "var(--color-danger-surface)",
            borderColor: "var(--color-danger)",
          }}
          role="alert"
        >
          <p>{error}</p>
          {quotaExhausted && (
            <p className="mt-2 text-text-muted">
              Scanning a candidate&apos;s shared QR link stays free and is never metered.{" "}
              <Link href="/employer/billing" className="font-medium text-brand hover:underline">
                See plans
              </Link>
            </p>
          )}
        </div>
      )}

      {outcome && result && (
        <div className="mt-6">
          <OutcomePanel outcome={outcome} detail={result.reason}>
            <SubjectNote result={result} />
            <ChainEvidence result={result} />
          </OutcomePanel>
        </div>
      )}
    </>
  );
}

/**
 * The evidence behind the verdict.
 *
 * Shown on every outcome, including a clean pass. A verifier who can recompute
 * the hash themselves and see it match does not have to take the platform's word
 * for the green tick — and on a TAMPERED result the mismatch between these two
 * values *is* the finding.
 */
function ChainEvidence({ result }: { result: VerifyResponse }) {
  const chain = result.chain as { tx_hash?: string; block_number?: number; chain_id?: number };
  const matches =
    Boolean(result.expected_hash) && result.expected_hash === result.computed_hash;

  return (
    <div className="mt-4 border-t border-border pt-3 text-xs text-text-subtle">
      <p className="break-all">
        <span className="font-medium text-text-muted">Document SHA-256:</span>{" "}
        <span className="font-mono">{result.document_sha256}</span>
      </p>
      {result.expected_hash && (
        <p className="mt-1 break-all">
          <span className="font-medium text-text-muted">Ledger fingerprint:</span>{" "}
          <span className="font-mono">{result.expected_hash}</span>{" "}
          {matches ? "· recomputed and matches" : "· does NOT match the recomputed value"}
        </p>
      )}
      {chain?.tx_hash && (
        <p className="mt-1 break-all">
          <span className="font-medium text-text-muted">Anchored in:</span>{" "}
          <TxLink hash={chain.tx_hash} />
          {chain.block_number ? ` · block ${chain.block_number}` : ""}
          {chain.chain_id ? ` · chain ${chain.chain_id}` : ""}
        </p>
      )}
    </div>
  );
}

/**
 * The honest limit on the subject guarantee.
 *
 * A holder whose citizenship number no issuer has attested cannot be checked.
 * Saying "we cannot confirm who this belongs to" is the truthful answer; saying
 * nothing would let a recruiter assume the name was verified when it was not.
 */
function SubjectNote({ result }: { result: VerifyResponse }) {
  if (result.subject_check_available && result.subject_match) {
    return (
      <p className="text-sm text-text">
        The citizenship number you entered matches the person this was issued to.
      </p>
    );
  }
  if (result.subject_check_available && result.subject_match === false) {
    return (
      <p className="text-sm text-text">
        The citizenship number you entered does <strong>not</strong> match the
        person this was issued to.
      </p>
    );
  }
  return (
    <p className="text-sm text-text-muted">
      We could not check who this belongs to. This holder’s account is verified
      by email only — no institution has attested a citizenship number for them,
      so the document is genuine but its owner cannot be confirmed here.
    </p>
  );
}
