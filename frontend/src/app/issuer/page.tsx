"use client";

import {
  ActionGrid,
  ActionTile,
  EmptyState,
  ListCard,
  ListRow,
  SectionHeader,
  StatGrid,
  StatTile,
  StatusPill,
} from "@/components/ui/dashboard";
import { ErrorState, LoadingRows, LoadingStats } from "@/components/ui/form";
import { LedgerBanner } from "@/components/shell/ledger-banner";
import { errorMessage } from "@/lib/api/errors";
import { useActivity, useRecordStats, useRecords } from "@/lib/api/hooks";
import { anchorLabel, pillFor, recordTitle, shortHash, timeAgo } from "@/lib/api/types";

export default function IssuerDashboard() {
  const stats = useRecordStats();
  const records = useRecords();
  const activity = useActivity();

  return (
    <div className="mx-auto w-full max-w-5xl space-y-8">
      <LedgerBanner />

      {stats.isPending ? (
        <LoadingStats />
      ) : stats.isError ? (
        <ErrorState message={errorMessage(stats.error)} onRetry={() => void stats.refetch()} />
      ) : (
        <StatGrid>
          <StatTile label="Total issued" value={stats.data?.total ?? 0} />
          <StatTile
            label="Anchored"
            value={stats.data?.issued ?? 0}
            tone="verified"
            hint="Verifiable right now"
          />
          <StatTile
            label="Awaiting confirmation"
            value={stats.data?.offered ?? 0}
            tone="revoked"
            hint="Not yet on chain"
          />
          <StatTile label="Revoked" value={stats.data?.revoked ?? 0} />
        </StatGrid>
      )}

      {/* Surfaced only when it is non-zero. A permanent "0 pending anchors"
          tile trains people to ignore the row it lives in. */}
      {(stats.data?.pending_anchor ?? 0) > 0 && (
        <p
          className="rounded-[var(--radius-card)] border px-4 py-3 text-sm"
          style={{
            backgroundColor: "var(--color-superseded-surface)",
            borderColor: "var(--color-superseded-border)",
          }}
          role="status"
        >
          {stats.data?.pending_anchor} credential
          {stats.data?.pending_anchor === 1 ? " has" : "s have"} been confirmed by the holder and
          are queued for the ledger. They anchor automatically once the node accepts them.
        </p>
      )}

      <section aria-labelledby="quick-actions">
        <h2 id="quick-actions" className="mb-3 text-sm font-semibold tracking-tight">
          Quick actions
        </h2>
        <ActionGrid>
          <ActionTile
            href="/issuer/issue"
            label="Issue single"
            description="One person, by email"
            icon="plus"
            primary
          />
          <ActionTile
            href="/issuer/bulk"
            label="Bulk issue"
            description="A whole batch from a spreadsheet"
            icon="upload"
          />
          <ActionTile href="/issuer/history" label="History" icon="clock" />
          <ActionTile href="/issuer/activity" label="Ledger activity" icon="activity" />
        </ActionGrid>
      </section>

      <div className="grid gap-6 lg:grid-cols-2">
        <section aria-labelledby="recent-credentials">
          <SectionHeader title="Recent credentials" href="/issuer/history" />
          <h2 id="recent-credentials" className="sr-only">
            Recent credentials
          </h2>

          {records.isPending ? (
            <LoadingRows />
          ) : (records.data?.length ?? 0) === 0 ? (
            <EmptyState
              icon="shield-check"
              title="Nothing issued yet"
              description="Issue a credential to one person, or upload a spreadsheet for a whole graduating batch."
            />
          ) : (
            <ListCard>
              {records.data?.slice(0, 5).map((record) => (
                <ListRow
                  key={record.id}
                  title={recordTitle(record)}
                  subtitle={`0x${record.record_hash.slice(0, 20)}…`}
                  meta={`${record.subject_email} · ${timeAgo(record.created_at)} · ${anchorLabel(record)}`}
                  trailing={<StatusPill state={pillFor(record.status)} />}
                />
              ))}
            </ListCard>
          )}
        </section>

        <section aria-labelledby="recent-activity">
          <SectionHeader title="Recent activity" href="/issuer/activity" />
          <h2 id="recent-activity" className="sr-only">
            Recent activity
          </h2>

          {activity.isPending ? (
            <LoadingRows />
          ) : (activity.data?.length ?? 0) === 0 ? (
            <EmptyState
              icon="activity"
              title="No activity yet"
              description="Every anchor, confirmation and revocation for this institution is recorded here."
            />
          ) : (
            <ListCard>
              {activity.data?.slice(0, 5).map((event) => (
                <ListRow
                  key={event.id}
                  title={event.label}
                  meta={[event.detail, timeAgo(event.created_at)].filter(Boolean).join(" · ")}
                  {...(event.tx_hash ? { subtitle: shortHash(event.tx_hash, 14) } : {})}
                />
              ))}
            </ListCard>
          )}
        </section>
      </div>
    </div>
  );
}
