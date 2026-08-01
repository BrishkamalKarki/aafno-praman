"use client";

import { Card, CardBody } from "@/components/ui/card";
import { EmptyState, ListCard, ListRow } from "@/components/ui/dashboard";
import { ErrorState, LoadingRows } from "@/components/ui/form";
import { LedgerBanner } from "@/components/shell/ledger-banner";
import { errorMessage } from "@/lib/api/errors";
import { useActivity, useLedgerStatus, useMyOrganization } from "@/lib/api/hooks";
import { formatDate, shortHash, timeAgo } from "@/lib/api/types";

/**
 * Every anchor attempt, confirmation and on-chain event for this institution.
 *
 * Read straight from the append-only audit table, which already records each of
 * these with its transaction hash. A second activity log kept in parallel would
 * eventually disagree with the first, and then neither would be evidence.
 */
export default function IssuerActivityPage() {
  const activity = useActivity();
  const ledger = useLedgerStatus();
  const organization = useMyOrganization();

  return (
    <div className="mx-auto w-full max-w-3xl space-y-6">
      <div>
        <h1 className="text-lg font-semibold tracking-tight">Ledger activity</h1>
        <p className="mt-1.5 text-sm text-text-muted">
          Every anchor attempt, confirmation, and on-chain event for this institution.
        </p>
      </div>

      <LedgerBanner />

      <Card>
        <CardBody className="grid gap-4 pt-5 sm:grid-cols-2">
          <Fact
            label="Chain"
            value={
              ledger.data?.ledger.ok
                ? `Connected · chain ${ledger.data.ledger.chain_id} · block ${ledger.data.ledger.block_number}`
                : "Unreachable"
            }
          />
          <Fact label="Registry contract" value={ledger.data?.ledger.contract_address ?? "—"} mono />
          <Fact
            label="This institution's signing address"
            value={organization.data?.chain_address ?? "—"}
            mono
          />
          <Fact
            label="Approved on chain"
            value={
              organization.data?.approved_at
                ? `${formatDate(organization.data.approved_at)} · ${shortHash(organization.data.approval_tx_hash, 14)}`
                : "—"
            }
          />
          <Fact label="Anchors confirmed" value={String(ledger.data?.local.confirmed_anchors ?? 0)} />
          <Fact label="Anchors pending" value={String(ledger.data?.local.pending_anchors ?? 0)} />
        </CardBody>
      </Card>

      <div>
        {activity.isPending ? (
          <LoadingRows rows={5} />
        ) : activity.isError ? (
          <ErrorState
            message={errorMessage(activity.error)}
            onRetry={() => void activity.refetch()}
          />
        ) : (activity.data?.length ?? 0) === 0 ? (
          <EmptyState
            icon="activity"
            title="Nothing has happened yet"
            description="Issue a credential and every step of its journey to the ledger is recorded here."
          />
        ) : (
          <ListCard>
            {activity.data?.map((event) => (
              <ListRow
                key={event.id}
                title={event.label}
                meta={[event.detail, event.actor_label, timeAgo(event.created_at)]
                  .filter(Boolean)
                  .join(" · ")}
                {...(event.tx_hash ? { subtitle: event.tx_hash } : {})}
              />
            ))}
          </ListCard>
        )}
      </div>
    </div>
  );
}

function Fact({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <div>
      <p className="text-xs font-medium text-text-subtle uppercase">{label}</p>
      <p className={`mt-1 break-all text-sm text-text${mono ? " font-mono text-xs" : ""}`}>
        {value}
      </p>
    </div>
  );
}
