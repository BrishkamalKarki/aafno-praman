"use client";

import { useMemo, useState } from "react";

import { OfferCard } from "@/components/citizen/offer-card";
import { Card, CardBody } from "@/components/ui/card";
import { EmptyState, ListCard, ListRow, StatusPill } from "@/components/ui/dashboard";
import { ErrorState, filterClass, LoadingRows } from "@/components/ui/form";
import { Icon } from "@/components/ui/icon";
import { TxLink } from "@/components/ui/tx-link";
import { errorMessage } from "@/lib/api/errors";
import { useOffers, usePassport } from "@/lib/api/hooks";
import {
  anchorLabel,
  formatDate,
  pillFor,
  recordTitle,
  shortHash,
  type CredentialRecord,
} from "@/lib/api/types";

/**
 * Everything ever issued to this holder, in one list.
 *
 * Offers sit at the top with their accept/decline buttons rather than as rows in
 * the table below: an unanswered offer is a decision, not a record.
 *
 * Every record carries its ledger state in plain words — "Anchored", "Pending
 * anchor", "Revoked on chain". A credential that has been consented to but not
 * yet written is a real state that occurs whenever the node is busy or briefly
 * down, and hiding it would make the platform look like it had lost something.
 */
export default function CredentialsPage() {
  const passport = usePassport();
  const offers = useOffers();
  const [expanded, setExpanded] = useState<string | null>(null);
  const [type, setType] = useState<"ALL" | "ACADEMIC" | "EXPERIENCE">("ALL");

  const records = useMemo(() => {
    const all = passport.data?.records ?? [];
    return all
      .filter((record) => record.status !== "OFFERED")
      .filter((record) => type === "ALL" || record.record_type === type);
  }, [passport.data, type]);

  return (
    <div className="mx-auto w-full max-w-3xl">
      <h1 className="text-lg font-semibold tracking-tight">All credentials</h1>
      <p className="mt-1.5 text-sm text-text-muted">
        Everything issued to you, with what is on the ledger for each one.
      </p>

      {(offers.data?.length ?? 0) > 0 && (
        <section aria-labelledby="awaiting" className="mt-6 space-y-3">
          <h2 id="awaiting" className="text-sm font-semibold tracking-tight">
            Waiting for your answer
          </h2>
          {offers.data?.map((offer) => (
            <OfferCard key={offer.id} offer={offer} />
          ))}
        </section>
      )}

      <div className="mt-6 flex flex-wrap gap-2">
        <select
          value={type}
          onChange={(event) => setType(event.target.value as typeof type)}
          className={filterClass}
          aria-label="Filter by credential type"
        >
          <option value="ALL">All types</option>
          <option value="ACADEMIC">Academic</option>
          <option value="EXPERIENCE">Work experience</option>
        </select>
      </div>

      <div className="mt-4">
        {passport.isPending ? (
          <LoadingRows rows={4} />
        ) : passport.isError ? (
          <ErrorState
            message={errorMessage(passport.error)}
            onRetry={() => void passport.refetch()}
          />
        ) : records.length === 0 ? (
          <EmptyState
            icon="shield-check"
            title="Nothing here yet"
            description="Credentials appear here once an institution or employer issues them to you and you confirm."
          />
        ) : (
          <ListCard>
            {records.map((record) => (
              <ListRow
                key={record.id}
                title={recordTitle(record)}
                subtitle={`0x${record.record_hash.slice(0, 24)}…`}
                meta={`${record.issuer_name} · ${anchorLabel(record)}`}
                trailing={
                  <div className="flex items-center gap-2">
                    <StatusPill state={pillFor(record.status)} />
                    <button
                      type="button"
                      onClick={() =>
                        setExpanded((current) => (current === record.id ? null : record.id))
                      }
                      className="rounded-[var(--radius-control)] p-1.5 text-text-subtle hover:bg-surface-muted"
                      aria-expanded={expanded === record.id}
                      aria-label={`Details for ${recordTitle(record)}`}
                    >
                      <Icon
                        name="chevron-down"
                        size={16}
                        className={expanded === record.id ? "rotate-180" : undefined}
                      />
                    </button>
                  </div>
                }
              />
            ))}
          </ListCard>
        )}
      </div>

      {expanded && <RecordDetail record={records.find((record) => record.id === expanded)} />}
    </div>
  );
}

function RecordDetail({ record }: { record: CredentialRecord | undefined }) {
  if (!record) return null;

  const academic = record.record_type === "ACADEMIC";

  return (
    <Card className="mt-4">
      <CardBody className="grid gap-4 pt-5 sm:grid-cols-2">
        <Field label="Credential" value={recordTitle(record)} />
        <Field label="Issued by" value={record.issuer_name} />
        {academic ? (
          <>
            <Field label="Registration number" value={record.detail.registration_number} />
            <Field label="Graduated" value={formatDate(record.detail.graduation_date)} />
            <Field label="Result" value={record.detail.cgpa ?? record.detail.percentage} />
            <Field label="Major" value={record.detail.major} />
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

        <div className="sm:col-span-2">
          <p className="text-xs font-medium text-text-subtle uppercase">Ledger</p>
          <p className="mt-1 text-sm text-text">{anchorLabel(record)}</p>
          {/* The transaction hash is the whole point of anchoring: it is what
              lets a sceptical verifier check the claim without trusting us. */}
          {record.anchor?.tx_hash && (
            <p className="mt-1 break-all text-xs text-text-subtle">
              tx <TxLink hash={record.anchor.tx_hash} /> · block{" "}
              {record.anchor.block_number ?? "—"} · chain {record.anchor.chain_id ?? "—"}
            </p>
          )}
          <p className="mt-2 break-all font-mono text-xs text-text-subtle">
            fingerprint 0x{record.record_hash}
          </p>
          {record.anchor?.issuer_address && (
            <p className="mt-1 font-mono text-xs text-text-subtle">
              signed by {shortHash(record.anchor.issuer_address, 12)}
            </p>
          )}
        </div>
      </CardBody>
    </Card>
  );
}

function Field({ label, value }: { label: string; value: string | null | undefined }) {
  return (
    <div>
      <p className="text-xs font-medium text-text-subtle uppercase">{label}</p>
      <p className="mt-1 text-sm text-text">{value || "—"}</p>
    </div>
  );
}
