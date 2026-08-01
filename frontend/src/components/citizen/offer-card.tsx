"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { FormError, textareaClass } from "@/components/ui/form";
import { errorMessage } from "@/lib/api/errors";
import { useAnswerOffer } from "@/lib/api/hooks";
import { formatDate, type CredentialOffer } from "@/lib/api/types";
import { useToast } from "@/lib/toast";

/**
 * A credential someone says they issued you, and the two buttons that decide it.
 *
 * Everything the holder is consenting to is on screen before either button: the
 * issuer, the title, and the exact hash that will be published. Consenting to a
 * value you cannot see is not consent, and the backend computes that hash at
 * offer time precisely so it can be shown here rather than after the fact.
 *
 * Declining asks for a reason but does not require one. The reason goes to the
 * issuer so a mistyped address gets corrected; demanding it would mean someone
 * who simply is not this person cannot say so.
 */
export function OfferCard({ offer }: { offer: CredentialOffer }) {
  const answer = useAnswerOffer();
  const { notify } = useToast();

  const [showDecline, setShowDecline] = useState(false);
  const [showDetail, setShowDetail] = useState(false);
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function respond(action: "accept" | "decline") {
    setError(null);
    try {
      await answer.mutateAsync({
        id: offer.id,
        action,
        ...(action === "decline" ? { reason } : {}),
      });
      notify(
        action === "accept"
          ? "Confirmed. It is being written to the ledger now."
          : "Declined. Nothing was published.",
        action === "accept" ? "success" : "info",
      );
    } catch (caught) {
      setError(errorMessage(caught, "Could not send your answer. Please try again."));
    }
  }

  const busy = answer.isPending;

  return (
    <div
      className="rounded-[var(--radius-card)] border p-5"
      style={{
        backgroundColor: "var(--color-revoked-surface)",
        borderColor: "var(--color-revoked-border)",
      }}
    >
      <p className="text-sm text-text">
        <span className="font-semibold">{offer.issuer_name}</span> says they issued you a
        credential.
      </p>
      <p className="mt-1 text-lg font-semibold tracking-tight">{offer.title}</p>
      <p className="mt-2 text-sm text-text-muted">
        Nothing is published until you confirm. If you accept, its fingerprint is written to
        the public ledger — the certificate itself never leaves our servers.
      </p>
      {offer.offer_expires_at && (
        <p className="mt-1 text-xs text-text-subtle">
          This offer expires on {formatDate(offer.offer_expires_at)}.
        </p>
      )}

      {showDetail && (
        <dl className="mt-4 space-y-2 rounded-[var(--radius-card)] border border-border bg-surface p-4 text-sm">
          <Detail label="Issued to" value={offer.subject_full_name} />
          <Detail label="Email on file" value={offer.subject_email} />
          {offer.record_type === "ACADEMIC" ? (
            <>
              <Detail label="Registration number" value={offer.detail.registration_number} />
              <Detail label="Graduated" value={formatDate(offer.detail.graduation_date)} />
            </>
          ) : (
            <>
              <Detail label="Employment" value={offer.detail.employment_type} />
              <Detail
                label="Period"
                value={`${formatDate(offer.detail.start_date)} – ${
                  offer.detail.is_current ? "present" : formatDate(offer.detail.end_date)
                }`}
              />
            </>
          )}
          <div>
            <dt className="text-xs font-medium text-text-subtle">
              Fingerprint that will be published
            </dt>
            <dd className="break-hash mt-0.5 font-mono text-xs text-text-muted">
              0x{offer.record_hash}
            </dd>
          </div>
        </dl>
      )}

      {error && (
        <div className="mt-4">
          <FormError message={error} />
        </div>
      )}

      {showDecline ? (
        <div className="mt-4 space-y-3">
          <label htmlFor={`reason-${offer.id}`} className="block text-sm font-medium">
            Why is this not yours?{" "}
            <span className="font-normal text-text-subtle">(optional)</span>
          </label>
          <textarea
            id={`reason-${offer.id}`}
            rows={3}
            maxLength={500}
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            className={textareaClass}
            placeholder="e.g. I never studied there, or this is a different person with my name"
          />
          <p className="text-xs text-text-subtle">
            This is sent to {offer.issuer_name} so they can correct their records.
          </p>
          <div className="flex flex-wrap gap-2">
            <Button variant="danger" loading={busy} onClick={() => void respond("decline")}>
              Decline this credential
            </Button>
            <Button variant="ghost" disabled={busy} onClick={() => setShowDecline(false)}>
              Go back
            </Button>
          </div>
        </div>
      ) : (
        <div className="mt-4 flex flex-wrap gap-2">
          <Button loading={busy} onClick={() => void respond("accept")}>
            Yes, this is mine
          </Button>
          <Button variant="secondary" disabled={busy} onClick={() => setShowDecline(true)}>
            Not me
          </Button>
          <Button variant="ghost" onClick={() => setShowDetail((current) => !current)}>
            {showDetail ? "Hide details" : "View details"}
          </Button>
        </div>
      )}
    </div>
  );
}

function Detail({ label, value }: { label: string; value: string | null | undefined }) {
  return (
    <div>
      <dt className="text-xs font-medium text-text-subtle">{label}</dt>
      <dd className="mt-0.5 text-sm text-text">{value || "—"}</dd>
    </div>
  );
}
