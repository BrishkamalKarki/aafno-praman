"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardBody } from "@/components/ui/card";
import { EmptyState, ListCard, ListRow, StatusPill } from "@/components/ui/dashboard";
import {
  ErrorState,
  filterClass,
  FormError,
  LoadingRows,
  textareaClass,
} from "@/components/ui/form";
import { errorMessage } from "@/lib/api/errors";
import { useRecords, useRevokeRecord } from "@/lib/api/hooks";
import {
  anchorLabel,
  formatDate,
  pillFor,
  recordTitle,
  type CredentialRecord,
} from "@/lib/api/types";
import { useToast } from "@/lib/toast";

/**
 * Everything this institution has issued, plus the one post-issuance action it
 * has.
 *
 * There is no edit. Editing an anchored record is definitionally tampering — the
 * hash would no longer match what the ledger holds — so a mistake is withdrawn
 * with a stated reason and re-issued, both of which leave a trail.
 *
 * Search and status filtering are server-side (`search_fields` and
 * `filterset_fields` on the viewset) rather than filtering an already-fetched
 * page, which would only ever search the first twenty rows.
 */

const STATUSES = [
  { value: "", label: "All statuses" },
  { value: "OFFERED", label: "Awaiting confirmation" },
  { value: "PENDING_ANCHOR", label: "Pending anchor" },
  { value: "ISSUED", label: "Issued & anchored" },
  { value: "DECLINED", label: "Declined by holder" },
  { value: "EXPIRED", label: "Offer expired" },
  { value: "REVOKED", label: "Revoked" },
] as const;

export default function IssuerHistoryPage() {
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("");
  const [revoking, setRevoking] = useState<CredentialRecord | null>(null);

  const records = useRecords({ search: query, status });

  return (
    <div className="mx-auto w-full max-w-3xl">
      <h1 className="text-lg font-semibold tracking-tight">Credential history</h1>
      <p className="mt-1.5 text-sm text-text-muted">
        Everything this institution has issued, searchable by recipient or fingerprint.
      </p>

      <div className="mt-4 flex flex-wrap gap-2">
        <input
          type="search"
          placeholder="Search by name, email, or hash"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          className={`${filterClass} min-w-48 flex-1`}
          aria-label="Search credentials"
        />
        <select
          value={status}
          onChange={(event) => setStatus(event.target.value)}
          className={filterClass}
          aria-label="Filter by status"
        >
          {STATUSES.map((entry) => (
            <option key={entry.value} value={entry.value}>
              {entry.label}
            </option>
          ))}
        </select>
      </div>

      {revoking && <RevokePanel record={revoking} onClose={() => setRevoking(null)} />}

      <div className="mt-4">
        {records.isPending ? (
          <LoadingRows rows={4} />
        ) : records.isError ? (
          <ErrorState
            message={errorMessage(records.error)}
            onRetry={() => void records.refetch()}
          />
        ) : (records.data?.length ?? 0) === 0 ? (
          <EmptyState
            icon="search"
            title={query || status ? "No matches" : "Nothing issued yet"}
            description={
              query || status
                ? "Try a different search or status filter."
                : "Credentials you issue appear here with their ledger status."
            }
          />
        ) : (
          <ListCard>
            {records.data?.map((record) => (
              <ListRow
                key={record.id}
                title={recordTitle(record)}
                subtitle={`0x${record.record_hash.slice(0, 24)}…`}
                meta={`${record.subject_email} · ${formatDate(record.created_at)} · ${anchorLabel(record)}`}
                trailing={
                  <div className="flex shrink-0 items-center gap-2">
                    <StatusPill state={pillFor(record.status)} />
                    {/* Only an anchored record can be revoked — there is
                        nothing on chain to withdraw before that. */}
                    {record.status === "ISSUED" && (
                      <Button variant="ghost" size="sm" onClick={() => setRevoking(record)}>
                        Revoke
                      </Button>
                    )}
                  </div>
                }
              />
            ))}
          </ListCard>
        )}
      </div>
    </div>
  );
}

/**
 * Revocation, with a mandatory reason.
 *
 * The reason is shown to anyone who later verifies the credential. "Revoked"
 * with no explanation is indistinguishable from an administrative error and
 * leaves the holder with no way to contest it.
 */
function RevokePanel({ record, onClose }: { record: CredentialRecord; onClose: () => void }) {
  const revoke = useRevokeRecord();
  const { notify } = useToast();
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      await revoke.mutateAsync({ id: record.id, reason: reason.trim() });
      notify("Revoked. Verifiers now see this as withdrawn.", "info");
      onClose();
    } catch (caught) {
      setError(errorMessage(caught, "Could not revoke this credential."));
    }
  }

  return (
    <Card className="mt-4">
      <CardBody className="pt-5">
        <h2 className="text-sm font-semibold tracking-tight">
          Revoke “{recordTitle(record)}” for {record.subject_full_name}
        </h2>
        <p className="mt-1 text-sm text-text-muted">
          This is written to the ledger and cannot be undone. The credential stays visible and is
          reported as revoked, with your reason attached — it is not erased.
        </p>

        <form onSubmit={submit} className="mt-4 space-y-3">
          <FormError message={error} />

          <div>
            <label htmlFor="revoke-reason" className="block text-sm font-medium">
              Reason
            </label>
            <textarea
              id="revoke-reason"
              required
              rows={3}
              maxLength={500}
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              className={textareaClass}
              placeholder="e.g. Issued in error — duplicate of an earlier record"
            />
          </div>

          <div className="flex flex-wrap gap-2">
            <Button type="submit" variant="danger" loading={revoke.isPending}>
              Revoke credential
            </Button>
            <Button type="button" variant="ghost" onClick={onClose}>
              Cancel
            </Button>
          </div>
        </form>
      </CardBody>
    </Card>
  );
}
