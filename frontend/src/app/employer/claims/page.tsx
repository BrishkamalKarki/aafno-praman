"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardBody } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/dashboard";
import { ErrorState, FormError, LoadingRows, textareaClass } from "@/components/ui/form";
import { errorMessage } from "@/lib/api/errors";
import { useClaims, useReviewClaim } from "@/lib/api/hooks";
import { formatDate, recordTitle, timeAgo, type CredentialRecord } from "@/lib/api/types";
import { useToast } from "@/lib/toast";

/**
 * The employer's inbox for claims former employees have logged.
 *
 * The other direction of issuance. An ex-employee states where they worked and
 * when; nothing is hashed and nothing reaches the chain until someone here
 * endorses it, because an unendorsed claim is just an assertion by the candidate
 * and anchoring it would let anyone write self-attested "verified" employment
 * onto the ledger.
 *
 * Rejection requires a reason, and endorsement does not. That asymmetry is
 * deliberate: a claim that disappears with no explanation is indistinguishable
 * from a bug, and the person who mistyped a start date has no way to correct it.
 */
export default function ClaimsPage() {
  const claims = useClaims();

  return (
    <div className="mx-auto w-full max-w-3xl">
      <h1 className="text-lg font-semibold tracking-tight">Claims to review</h1>
      <p className="mt-1.5 text-sm text-text-muted">
        Former employees who have logged their history at this company. Endorsing one anchors it
        to the ledger under your organisation&apos;s name.
      </p>

      <div className="mt-6 space-y-4">
        {claims.isPending ? (
          <LoadingRows rows={2} />
        ) : claims.isError ? (
          <ErrorState message={errorMessage(claims.error)} onRetry={() => void claims.refetch()} />
        ) : (claims.data?.length ?? 0) === 0 ? (
          <EmptyState
            icon="inbox"
            title="Nothing waiting"
            description="When someone logs employment at this company, it appears here for you to confirm or dispute."
          />
        ) : (
          claims.data?.map((claim) => <ClaimCard key={claim.id} claim={claim} />)
        )}
      </div>
    </div>
  );
}

function ClaimCard({ claim }: { claim: CredentialRecord }) {
  const review = useReviewClaim();
  const { notify } = useToast();

  const [showReject, setShowReject] = useState(false);
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function decide(action: "endorse" | "reject") {
    setError(null);
    try {
      await review.mutateAsync({ id: claim.id, action, note: note.trim() });
      notify(
        action === "endorse"
          ? "Endorsed. It is being anchored to the ledger now."
          : "Rejected. The claimant has been told why.",
        action === "endorse" ? "success" : "info",
      );
    } catch (caught) {
      setError(errorMessage(caught, "Could not record your decision."));
    }
  }

  return (
    <Card>
      <CardBody className="pt-5">
        <p className="text-sm text-text">
          <span className="font-semibold">{claim.subject_full_name}</span> says they worked here.
        </p>
        <p className="mt-1 text-lg font-semibold tracking-tight">{recordTitle(claim)}</p>

        <dl className="mt-3 grid gap-3 text-sm sm:grid-cols-2">
          <Field label="Email" value={claim.subject_email} />
          <Field label="Employment type" value={claim.detail.employment_type} />
          <Field label="Started" value={formatDate(claim.detail.start_date)} />
          <Field
            label="Ended"
            value={claim.detail.is_current ? "Still employed" : formatDate(claim.detail.end_date)}
          />
          <Field label="Department" value={claim.detail.department} />
          <Field label="Submitted" value={timeAgo(claim.created_at)} />
          {claim.detail.responsibilities && (
            <div className="sm:col-span-2">
              <dt className="text-xs font-medium text-text-subtle uppercase">Responsibilities</dt>
              <dd className="mt-1 text-sm text-text">{claim.detail.responsibilities}</dd>
            </div>
          )}
        </dl>

        {error && (
          <div className="mt-4">
            <FormError message={error} />
          </div>
        )}

        {showReject ? (
          <div className="mt-4 space-y-3">
            <label htmlFor={`note-${claim.id}`} className="block text-sm font-medium">
              Why are you rejecting this?
            </label>
            <textarea
              id={`note-${claim.id}`}
              required
              rows={3}
              maxLength={500}
              value={note}
              onChange={(event) => setNote(event.target.value)}
              className={textareaClass}
              placeholder="e.g. The dates do not match our records — they left in March, not June"
            />
            <p className="text-xs text-text-subtle">
              Sent to {claim.subject_full_name} so an honest mistake can be corrected.
            </p>
            <div className="flex flex-wrap gap-2">
              <Button
                variant="danger"
                loading={review.isPending}
                disabled={!note.trim()}
                onClick={() => void decide("reject")}
              >
                Reject claim
              </Button>
              <Button variant="ghost" onClick={() => setShowReject(false)}>
                Go back
              </Button>
            </div>
          </div>
        ) : (
          <div className="mt-4 flex flex-wrap gap-2">
            <Button loading={review.isPending} onClick={() => void decide("endorse")}>
              Confirm and anchor
            </Button>
            <Button variant="secondary" onClick={() => setShowReject(true)}>
              Dispute this
            </Button>
          </div>
        )}
      </CardBody>
    </Card>
  );
}

function Field({ label, value }: { label: string; value: string | null | undefined }) {
  return (
    <div>
      <dt className="text-xs font-medium text-text-subtle uppercase">{label}</dt>
      <dd className="mt-1 text-sm text-text">{value || "—"}</dd>
    </div>
  );
}
