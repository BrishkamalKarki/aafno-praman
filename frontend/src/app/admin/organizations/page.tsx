"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardBody } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/dashboard";
import { ErrorState, filterClass, FormError, LoadingRows, textareaClass } from "@/components/ui/form";
import { errorMessage } from "@/lib/api/errors";
import { useOrganizationTransition, useRegistrarOrganizations } from "@/lib/api/hooks";
import { formatDate, shortHash, timeAgo, type RegistrarOrganization } from "@/lib/api/types";
import { useToast } from "@/lib/toast";

/**
 * Organisation management — the root of trust, as a screen.
 *
 * Four transitions and no generic edit, matching the API: an organisation's
 * status may only change through a transition that produces a chain transaction
 * and an audit entry, never a stray field update.
 *
 * Suspension is not retroactive, and the copy says so. Credentials issued while
 * an institution was accredited stay verifiable — punishing thousands of
 * graduates for their college's later misconduct would be unjust, and would be a
 * reason for nobody to trust the platform. What stops is the ability to issue
 * anything new.
 */

const TABS = [
  { value: "PENDING", label: "Awaiting review" },
  { value: "APPROVED", label: "Approved" },
  { value: "SUSPENDED", label: "Suspended" },
  { value: "REJECTED", label: "Rejected" },
  { value: "", label: "All" },
] as const;

export default function OrganizationsPage() {
  const [status, setStatus] = useState<string>("PENDING");
  const organizations = useRegistrarOrganizations(status || undefined);

  return (
    <div className="mx-auto w-full max-w-3xl">
      <h1 className="text-lg font-semibold tracking-tight">Organisations</h1>
      <p className="mt-1.5 max-w-xl text-sm text-text-muted">
        Who may issue credentials on this platform. Approving an organisation registers its
        signing key on the ledger; everything it issues afterwards inherits its authority from
        that decision.
      </p>

      <div className="mt-4 flex flex-wrap gap-2">
        <select
          value={status}
          onChange={(event) => setStatus(event.target.value)}
          className={filterClass}
          aria-label="Filter by status"
        >
          {TABS.map((tab) => (
            <option key={tab.value} value={tab.value}>
              {tab.label}
            </option>
          ))}
        </select>
      </div>

      <div className="mt-4 space-y-4">
        {organizations.isPending ? (
          <LoadingRows rows={3} />
        ) : organizations.isError ? (
          <ErrorState
            message={errorMessage(organizations.error)}
            onRetry={() => void organizations.refetch()}
          />
        ) : (organizations.data?.length ?? 0) === 0 ? (
          <EmptyState
            icon="building"
            title="Nothing here"
            description={
              status === "PENDING"
                ? "No applications are waiting. New organisations you create from the admin console are approved on the spot."
                : "No organisations match this filter."
            }
          />
        ) : (
          organizations.data?.map((organization) => (
            <OrganizationCard key={organization.id} organization={organization} />
          ))
        )}
      </div>
    </div>
  );
}

function OrganizationCard({ organization }: { organization: RegistrarOrganization }) {
  const transition = useOrganizationTransition();
  const { notify } = useToast();

  const [prompting, setPrompting] = useState<"reject" | "suspend" | null>(null);
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function act(action: "approve" | "reject" | "suspend" | "reinstate") {
    setError(null);
    try {
      await transition.mutateAsync({
        id: organization.id,
        action,
        ...(action === "reject" || action === "suspend" ? { reason: reason.trim() } : {}),
      });
      notify(
        {
          approve: "Approved and registered on the ledger.",
          reject: "Application rejected.",
          suspend: "Suspended. Existing credentials stay verifiable.",
          reinstate: "Reinstated. They can issue again.",
        }[action],
        action === "approve" || action === "reinstate" ? "success" : "info",
      );
      setPrompting(null);
      setReason("");
    } catch (caught) {
      setError(errorMessage(caught, "Could not complete that. Nothing has changed."));
    }
  }

  const busy = transition.isPending;

  return (
    <Card>
      <CardBody className="pt-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="text-base font-semibold tracking-tight">{organization.legal_name}</p>
            <p className="mt-0.5 text-sm text-text-muted">
              {organization.kind === "INSTITUTION" ? "Educational institution" : "Employer"} ·{" "}
              {organization.registration_number}
            </p>
          </div>
          <StatusBadge status={organization.status} />
        </div>

        <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2">
          <Field label="Contact" value={organization.contact_email} />
          <Field
            label="Applicant"
            value={
              organization.applicant?.full_name
                ? `${organization.applicant.full_name} (${organization.applicant.email})`
                : "—"
            }
          />
          <Field label="Applied" value={timeAgo(organization.created_at)} />
          <Field label="Members" value={String(organization.member_count)} />
          <Field label="Credentials issued" value={String(organization.issued_count)} />
          <Field label="Plan" value={organization.plan} />
          {organization.chain_address && (
            <div className="sm:col-span-2">
              <dt className="text-xs font-medium text-text-subtle uppercase">
                On-chain identity
              </dt>
              <dd className="mt-1 font-mono text-xs break-all text-text-muted">
                {organization.chain_address}
                {organization.approval_tx_hash && (
                  <> · approved in {shortHash(organization.approval_tx_hash, 14)}</>
                )}
                {organization.approved_at && <> · {formatDate(organization.approved_at)}</>}
              </dd>
            </div>
          )}
          {organization.status_reason && (
            <div className="sm:col-span-2">
              <dt className="text-xs font-medium text-text-subtle uppercase">Reason on file</dt>
              <dd className="mt-1 text-sm text-text">{organization.status_reason}</dd>
            </div>
          )}
        </dl>

        {error && (
          <div className="mt-4">
            <FormError message={error} />
          </div>
        )}

        {prompting ? (
          <div className="mt-4 space-y-3">
            <label htmlFor={`reason-${organization.id}`} className="block text-sm font-medium">
              Why are you {prompting === "reject" ? "rejecting" : "suspending"} them?
            </label>
            <textarea
              id={`reason-${organization.id}`}
              required
              rows={3}
              maxLength={500}
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              className={textareaClass}
              placeholder={
                prompting === "reject"
                  ? "e.g. Accreditation could not be confirmed with the UGC"
                  : "e.g. Under investigation following a records audit"
              }
            />
            {/* The reason is mandatory server-side: an organisation told only
                "suspended" has no way to fix the problem it was suspended for. */}
            <p className="text-xs text-text-subtle">
              Shown to the organisation and recorded permanently in the audit log.
              {prompting === "suspend" &&
                " Credentials they have already issued stay verifiable — only new issuance stops."}
            </p>
            <div className="flex flex-wrap gap-2">
              <Button
                variant="danger"
                loading={busy}
                disabled={!reason.trim()}
                onClick={() => void act(prompting)}
              >
                {prompting === "reject" ? "Reject application" : "Suspend issuer"}
              </Button>
              <Button variant="ghost" onClick={() => setPrompting(null)}>
                Cancel
              </Button>
            </div>
          </div>
        ) : (
          <div className="mt-4 flex flex-wrap gap-2">
            {organization.status === "PENDING" && (
              <>
                <Button loading={busy} onClick={() => void act("approve")}>
                  Approve and register on chain
                </Button>
                <Button variant="secondary" onClick={() => setPrompting("reject")}>
                  Reject
                </Button>
              </>
            )}
            {organization.status === "APPROVED" && (
              <Button variant="secondary" onClick={() => setPrompting("suspend")}>
                Suspend issuing
              </Button>
            )}
            {organization.status === "SUSPENDED" && (
              <Button loading={busy} onClick={() => void act("reinstate")}>
                Reinstate
              </Button>
            )}
            {organization.status === "REJECTED" && (
              <p className="text-sm text-text-subtle">
                Rejected applications are kept for the record and cannot be reopened here.
              </p>
            )}
          </div>
        )}
      </CardBody>
    </Card>
  );
}

const STATUS_TOKEN: Record<string, string> = {
  PENDING: "revoked",
  APPROVED: "verified",
  SUSPENDED: "tampered",
  REJECTED: "notfound",
};

function StatusBadge({ status }: { status: string }) {
  const token = STATUS_TOKEN[status] ?? "notfound";
  return (
    <span
      className="inline-flex shrink-0 items-center rounded-full border px-2.5 py-1 text-xs font-medium"
      style={{
        color: `var(--color-${token})`,
        backgroundColor: `var(--color-${token}-surface)`,
        borderColor: `var(--color-${token}-border)`,
      }}
    >
      {status.charAt(0) + status.slice(1).toLowerCase()}
    </span>
  );
}

function Field({ label, value }: { label: string; value: string | null | undefined }) {
  return (
    <div>
      <dt className="text-xs font-medium text-text-subtle uppercase">{label}</dt>
      <dd className="mt-1 break-words text-sm text-text">{value || "—"}</dd>
    </div>
  );
}
