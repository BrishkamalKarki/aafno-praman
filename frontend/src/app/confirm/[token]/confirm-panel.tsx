"use client";

import { useCallback, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardBody } from "@/components/ui/card";
import { ApiError, apiFetch } from "@/lib/api/client";

interface OfferPreview {
  record_id: string;
  issuer_name: string;
  subject_name: string;
  subject_email: string;
  title: string;
  record_hash: string;
  offer_expires_at: string;
}

type Phase = "loading" | "ready" | "confirmed" | "declined" | "error";

export function ConfirmPanel({ token }: { token: string }) {
  const [phase, setPhase] = useState<Phase>("loading");
  const [offer, setOffer] = useState<OfferPreview | null>(null);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [showDecline, setShowDecline] = useState(false);
  const [reason, setReason] = useState("");

  useEffect(() => {
    let cancelled = false;
    apiFetch<OfferPreview>(`/credentials/confirm/${token}/`, { anonymous: true })
      .then((data) => {
        if (cancelled) return;
        setOffer(data);
        setPhase("ready");
      })
      .catch((error: unknown) => {
        if (cancelled) return;
        setMessage(
          error instanceof ApiError
            ? error.message
            : "We could not load this confirmation link.",
        );
        setPhase("error");
      });
    return () => {
      cancelled = true;
    };
  }, [token]);

  const answer = useCallback(
    async (action: "accept" | "decline") => {
      setBusy(true);
      try {
        await apiFetch(`/credentials/confirm/${token}/${action}/`, {
          method: "POST",
          anonymous: true,
          ...(action === "decline" ? { body: { reason } } : {}),
        });
        setPhase(action === "accept" ? "confirmed" : "declined");
      } catch (error) {
        setMessage(
          error instanceof ApiError ? error.message : "Something went wrong.",
        );
        setPhase("error");
      } finally {
        setBusy(false);
      }
    },
    [token, reason],
  );

  if (phase === "loading") {
    return (
      <Card>
        <CardBody className="pt-5">
          <p className="text-sm text-text-muted" role="status">
            Loading your credential…
          </p>
        </CardBody>
      </Card>
    );
  }

  if (phase === "error") {
    return (
      <Outcome
        token="tampered"
        heading="This link is no longer valid"
        body={message}
        hint="Links expire after a week and can only be used once. Ask the organisation that issued your credential to send a new one."
      />
    );
  }

  if (phase === "confirmed") {
    return (
      <Outcome
        token="verified"
        heading="Confirmed"
        body="Your credential is being written to the ledger and will appear in your dashboard shortly."
        hint="You can now create share links to prove it to employers, and see who has checked it."
      />
    );
  }

  if (phase === "declined") {
    return (
      <Outcome
        token="notfound"
        heading="Declined"
        body="Nothing has been published."
        hint="The organisation that sent this has been told the address is not yours, so they can correct their records."
      />
    );
  }

  if (!offer) return null;

  return (
    <>
      <h1 className="text-2xl font-semibold tracking-tight text-balance">
        Is this credential yours?
      </h1>
      <p className="mt-2 text-sm leading-relaxed text-text-muted">
        <span className="font-medium text-text">{offer.issuer_name}</span> says
        they issued this to you. Nothing is published until you confirm.
      </p>

      <Card className="mt-6">
        <CardBody className="space-y-4 pt-5">
          <Field label="Credential" value={offer.title} />
          <Field label="Issued by" value={offer.issuer_name} />
          <Field label="Issued to" value={offer.subject_name} />
          <Field label="Email on file" value={offer.subject_email} />
          <div>
            <p className="text-xs font-medium text-text-subtle">
              Fingerprint that will be published
            </p>
            {/* Shown before the decision, not after. Consenting to a value you
                cannot see is not consent. */}
            <p className="break-hash mt-1 font-mono text-xs text-text-muted">
              0x{offer.record_hash}
            </p>
          </div>
        </CardBody>
      </Card>

      <div
        className="mt-4 rounded-[var(--radius-card)] border p-4 text-sm leading-relaxed"
        style={{
          backgroundColor: "var(--color-brand-subtle)",
          borderColor: "var(--color-brand-border)",
        }}
      >
        <p className="text-text">
          Confirming publishes only the fingerprint above — a one-way code. Your
          certificate, your name and your ID number are never written to the
          public ledger.
        </p>
      </div>

      {!showDecline ? (
        <div className="mt-6 flex flex-wrap gap-3">
          <Button size="lg" loading={busy} onClick={() => answer("accept")}>
            Yes, this is mine
          </Button>
          <Button size="lg" variant="secondary" onClick={() => setShowDecline(true)}>
            This is not me
          </Button>
        </div>
      ) : (
        <div className="mt-6 space-y-3">
          <label htmlFor="reason" className="block text-sm font-medium">
            Why is this not yours? <span className="text-text-subtle">(optional)</span>
          </label>
          <textarea
            id="reason"
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            rows={3}
            maxLength={500}
            className="w-full rounded-[var(--radius-control)] border border-border-strong bg-surface p-3 text-sm"
            placeholder="e.g. I never studied there, or this is a different person with my name"
          />
          <p className="text-xs text-text-subtle">
            This is sent to {offer.issuer_name} so they can correct their records.
          </p>
          <div className="flex flex-wrap gap-3">
            <Button variant="danger" loading={busy} onClick={() => answer("decline")}>
              Decline this credential
            </Button>
            <Button variant="ghost" onClick={() => setShowDecline(false)}>
              Go back
            </Button>
          </div>
        </div>
      )}

      <p className="mt-6 text-xs text-text-subtle">
        Do not forward this link — anyone who has it can answer on your behalf.
      </p>
    </>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs font-medium text-text-subtle">{label}</p>
      <p className="mt-0.5 text-sm text-text">{value}</p>
    </div>
  );
}

function Outcome({
  token,
  heading,
  body,
  hint,
}: {
  token: string;
  heading: string;
  body: string;
  hint: string;
}) {
  return (
    <section
      className="rounded-[var(--radius-card)] border p-6"
      style={{
        color: `var(--color-${token})`,
        backgroundColor: `var(--color-${token}-surface)`,
        borderColor: `var(--color-${token}-border)`,
      }}
      role="status"
      aria-live="assertive"
    >
      <h1 className="text-xl font-semibold tracking-tight">{heading}</h1>
      <p className="mt-2 text-sm leading-relaxed text-text">{body}</p>
      <p className="mt-2 text-sm leading-relaxed text-text-muted">{hint}</p>
    </section>
  );
}
