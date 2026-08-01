"use client";

import { useCallback, useEffect, useState } from "react";

import { Logo } from "@/components/brand/logo";
import { Button } from "@/components/ui/button";
import { Card, CardBody } from "@/components/ui/card";
import { FormError, inputClass, labelClass } from "@/components/ui/form";
import { Icon } from "@/components/ui/icon";
import { StatusPill } from "@/components/ui/dashboard";
import { TxLink } from "@/components/ui/tx-link";
import { ApiError, apiFetch } from "@/lib/api/client";
import { errorMessage } from "@/lib/api/errors";
import {
  anchorLabel,
  formatDate,
  pillFor,
  recordTitle,
  type CredentialRecord,
} from "@/lib/api/types";

/**
 * A holder's credentials, as the person they sent the link to sees them.
 *
 * Read-only and self-contained: everything a recruiter needs to decide is on
 * this one page, including the transaction hash for each anchored record so the
 * claim can be checked against the chain without trusting this page at all.
 */

interface SharedPassportResponse {
  owner_name: string;
  headline: string;
  shared_at: string;
  expires_at: string | null;
  masked: boolean;
  summary: { academic: number; experience: number; total: number };
  records: CredentialRecord[];
}

type Phase = "loading" | "locked" | "ready" | "gone";

export function SharedPassport({ token }: { token: string }) {
  const [phase, setPhase] = useState<Phase>("loading");
  const [data, setData] = useState<SharedPassportResponse | null>(null);
  const [message, setMessage] = useState("");

  const [passphrase, setPassphrase] = useState("");
  const [unlocking, setUnlocking] = useState(false);
  const [unlockError, setUnlockError] = useState<string | null>(null);

  const load = useCallback(
    async (secret?: string) => {
      const query = secret ? `?passphrase=${encodeURIComponent(secret)}` : "";
      return apiFetch<SharedPassportResponse>(`/verify/share/${token}/${query}`, {
        anonymous: true,
      });
    },
    [token],
  );

  useEffect(() => {
    let cancelled = false;

    load()
      .then((payload) => {
        if (cancelled) return;
        setData(payload);
        setPhase("ready");
      })
      .catch((error: unknown) => {
        if (cancelled) return;
        // 401 means the link is real but protected — a different situation from
        // a link that has been revoked, and the only one worth distinguishing.
        if (error instanceof ApiError && error.status === 401) {
          setPhase("locked");
          return;
        }
        setMessage(errorMessage(error, "This link is no longer available."));
        setPhase("gone");
      });

    return () => {
      cancelled = true;
    };
  }, [load]);

  async function unlock(event: React.FormEvent) {
    event.preventDefault();
    setUnlocking(true);
    setUnlockError(null);
    try {
      const payload = await load(passphrase);
      setData(payload);
      setPhase("ready");
    } catch (error) {
      setUnlockError(errorMessage(error, "That passphrase did not work."));
    } finally {
      setUnlocking(false);
    }
  }

  if (phase === "loading") {
    return (
      <Card>
        <CardBody className="pt-5">
          <p className="text-sm text-text-muted" role="status">
            Opening the shared credentials…
          </p>
        </CardBody>
      </Card>
    );
  }

  if (phase === "gone") {
    /**
     * One wording for revoked, expired and view-limit-reached alike. Telling a
     * stranger holding a stale link *which* of those happened would tell them
     * whether the person is still job-hunting.
     */
    return (
      <section
        role="status"
        className="rounded-[var(--radius-card)] border p-6"
        style={{
          color: "var(--color-notfound)",
          backgroundColor: "var(--color-notfound-surface)",
          borderColor: "var(--color-notfound-border)",
        }}
      >
        <h1 className="text-xl font-semibold tracking-tight">This link is no longer available</h1>
        <p className="mt-2 text-sm leading-relaxed text-text">{message}</p>
        <p className="mt-2 text-sm leading-relaxed text-text-muted">
          Share links can be revoked or given an expiry by the person who created them. Ask them
          for a new one.
        </p>
      </section>
    );
  }

  if (phase === "locked") {
    return (
      <>
        <h1 className="text-2xl font-semibold tracking-tight">This link is protected</h1>
        <p className="mt-2 text-sm text-text-muted">
          The person who shared it set a passphrase. They will have sent it to you separately.
        </p>

        <Card className="mt-6">
          <CardBody className="pt-5">
            <form onSubmit={unlock} className="space-y-4">
              <FormError message={unlockError} />
              <div>
                <label htmlFor="passphrase" className={labelClass}>
                  Passphrase
                </label>
                <input
                  id="passphrase"
                  type="password"
                  required
                  autoFocus
                  value={passphrase}
                  onChange={(event) => setPassphrase(event.target.value)}
                  className={inputClass}
                  autoComplete="off"
                />
              </div>
              <Button type="submit" size="lg" loading={unlocking}>
                Open credentials
              </Button>
            </form>
          </CardBody>
        </Card>
      </>
    );
  }

  if (!data) return null;

  return (
    <>
      <Logo className="text-sm text-brand" size={22} />
      <h1 className="mt-2 text-2xl font-semibold tracking-tight">{data.owner_name}</h1>
      {data.headline && <p className="mt-1 text-sm text-text-muted">{data.headline}</p>}

      <p className="mt-3 text-xs text-text-subtle">
        Shared {formatDate(data.shared_at)}
        {data.expires_at ? ` · expires ${formatDate(data.expires_at)}` : " · no expiry set"} ·{" "}
        {data.summary.academic} academic, {data.summary.experience} employment
      </p>

      {data.masked && (
        <p className="mt-3 text-xs text-text-subtle">
          Registration and citizenship numbers are shown only as their last few characters —
          enough to confirm a number you were already given, not enough to copy one down.
        </p>
      )}

      <div className="mt-6 space-y-4">
        {data.records.length === 0 ? (
          <Card>
            <CardBody className="pt-5">
              <p className="text-sm text-text-muted">
                This link does not include any confirmed credentials yet.
              </p>
            </CardBody>
          </Card>
        ) : (
          data.records.map((record) => <SharedRecord key={record.id} record={record} />)
        )}
      </div>

      <div
        className="mt-6 rounded-[var(--radius-card)] border p-4 text-sm leading-relaxed"
        style={{
          backgroundColor: "var(--color-brand-subtle)",
          borderColor: "var(--color-brand-border)",
        }}
      >
        <p className="text-text">
          Each fingerprint below was written to a public ledger by the issuing organisation. You
          can check any of them against the chain yourself — nothing here asks you to take our
          word for it.
        </p>
      </div>

      <p className="mt-4 text-xs text-text-subtle">
        The person who shared this can revoke the link at any time, and can see that it was
        opened.
      </p>
    </>
  );
}

function SharedRecord({ record }: { record: CredentialRecord }) {
  const academic = record.record_type === "ACADEMIC";

  return (
    <Card>
      <CardBody className="pt-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="text-base font-semibold tracking-tight">{recordTitle(record)}</p>
            <p className="mt-0.5 text-sm text-text-muted">
              {record.issuer_name}
              {record.issuer_status !== "APPROVED" && (
                // Said out loud rather than hidden. A degree issued while the
                // college was accredited stays valid if it is later suspended,
                // and a verifier deserves both halves of that fact.
                <span className="text-text-subtle"> · issuer since suspended</span>
              )}
            </p>
          </div>
          <StatusPill state={pillFor(record.status)} />
        </div>

        <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2">
          {academic ? (
            <>
              <Field label="Registration number" value={record.detail.registration_number} />
              <Field label="Graduated" value={formatDate(record.detail.graduation_date)} />
              <Field label="Major" value={record.detail.major} />
              <Field label="Result" value={record.detail.cgpa ?? record.detail.percentage} />
            </>
          ) : (
            <>
              <Field label="Employment type" value={record.detail.employment_type} />
              <Field label="Department" value={record.detail.department} />
              <Field label="Started" value={formatDate(record.detail.start_date)} />
              <Field
                label="Ended"
                value={
                  record.detail.is_current ? "Still employed" : formatDate(record.detail.end_date)
                }
              />
            </>
          )}
        </dl>

        <div className="mt-4 border-t border-border pt-3">
          <p className="flex items-center gap-1.5 text-xs font-medium text-text-muted">
            <Icon name="shield-check" size={14} className="shrink-0 text-brand" />
            {anchorLabel(record)}
          </p>
          {record.anchor?.tx_hash && (
            <p className="mt-1 break-all text-xs text-text-subtle">
              tx <TxLink hash={record.anchor.tx_hash} />
              {record.anchor.block_number ? ` · block ${record.anchor.block_number}` : ""}
              {record.anchor.chain_id ? ` · chain ${record.anchor.chain_id}` : ""}
            </p>
          )}
          <p className="mt-1 break-all font-mono text-xs text-text-subtle">
            fingerprint 0x{record.record_hash}
          </p>
        </div>
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
