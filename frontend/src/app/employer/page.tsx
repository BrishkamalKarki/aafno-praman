"use client";

import Link from "next/link";

import { QuotaMeter } from "@/components/employer/quota-meter";
import { LedgerBanner } from "@/components/shell/ledger-banner";
import { Button } from "@/components/ui/button";
import {
  ActionGrid,
  ActionTile,
  EmptyState,
  ListCard,
  ListRow,
  SectionHeader,
} from "@/components/ui/dashboard";
import { LoadingRows } from "@/components/ui/form";
import { OutcomeChip } from "@/components/verification/outcome-panel";
import { useClaims, useQuota, useVerificationHistory } from "@/lib/api/hooks";
import { timeAgo } from "@/lib/api/types";
import { planIdFor } from "@/lib/plans";
import { parseOutcome } from "@/lib/verification";

export default function EmployerDashboard() {
  const quota = useQuota();
  const history = useVerificationHistory();
  const claims = useClaims();

  return (
    <div className="mx-auto w-full max-w-5xl space-y-8">
      <LedgerBanner />

      <div className="grid gap-4 lg:grid-cols-[1fr_20rem]">
        <section
          aria-labelledby="verify-cta"
          className="rounded-[var(--radius-card)] border border-border bg-surface p-6"
        >
          <h2 id="verify-cta" className="text-lg font-semibold tracking-tight">
            Check a certificate
          </h2>
          <p className="mt-1.5 max-w-lg text-sm text-text-muted">
            Upload the PDF a candidate gave you. We tell you whether it is genuine — and whether
            it actually belongs to them.
          </p>
          <div className="mt-4 flex flex-wrap gap-2">
            <Link href="/employer/verify">
              <Button size="lg">Upload a certificate</Button>
            </Link>
          </div>
          {/* Stated up front rather than discovered at the paywall. An employer
              who finds the limit by being blocked mid-hire does not upgrade;
              they conclude the tool is unreliable. */}
          <p className="mt-3 text-xs text-text-subtle">
            Scanning a QR code on a printed certificate is always free and never counts against
            your allowance.
          </p>
        </section>

        <QuotaMeter
          plan={planIdFor(quota.data?.plan)}
          used={quota.data?.used ?? 0}
          limit={quota.data?.limit ?? null}
          {...(quota.data?.resets_at ? { resetsAt: quota.data.resets_at } : {})}
        />
      </div>

      {(claims.data?.length ?? 0) > 0 && (
        <section
          aria-labelledby="claims-cta"
          className="rounded-[var(--radius-card)] border p-5"
          style={{
            backgroundColor: "var(--color-revoked-surface)",
            borderColor: "var(--color-revoked-border)",
          }}
        >
          <h2 id="claims-cta" className="text-sm font-semibold tracking-tight">
            {claims.data?.length} former employee
            {claims.data?.length === 1 ? "" : "s"} waiting on you
          </h2>
          <p className="mt-1 text-sm text-text-muted">
            They have logged employment at this company and need someone here to confirm it.
            Nothing is anchored until you do.
          </p>
          <Link href="/employer/claims" className="mt-3 inline-block">
            <Button>Review claims</Button>
          </Link>
        </section>
      )}

      <section aria-labelledby="actions">
        <h2 id="actions" className="mb-3 text-sm font-semibold tracking-tight">
          Quick actions
        </h2>
        <ActionGrid>
          <ActionTile
            href="/employer/verify"
            label="Check validity"
            description="Upload a PDF — counts against your plan"
            icon="shield-check"
            primary
          />
          <ActionTile
            href="/employer/issue-experience"
            label="Issue experience letter"
            description="Never limited, on any plan"
            icon="upload"
          />
          <ActionTile
            href="/employer/bulk-issue-experience"
            label="Bulk issue experience letters"
            description="A whole team from a spreadsheet"
            icon="grid"
          />
          <ActionTile
            href="/employer/claims"
            label="Claims to review"
            description="Confirm a former employee's history"
            icon="inbox"
          />
          <ActionTile
            href="/employer/history"
            label="Verification history"
            description="Everything you have checked"
            icon="clock"
          />
          <ActionTile href="/employer/billing" label="Plan & usage" icon="activity" />
        </ActionGrid>
      </section>

      <section aria-labelledby="recent">
        <SectionHeader title="Recent verifications" href="/employer/history" />
        <h2 id="recent" className="sr-only">
          Recent verifications
        </h2>

        {history.isPending ? (
          <LoadingRows />
        ) : (history.data?.length ?? 0) === 0 ? (
          <EmptyState
            icon="search"
            title="Nothing checked yet"
            description="Upload a candidate's certificate and the result is recorded here."
          />
        ) : (
          <ListCard>
            {history.data?.slice(0, 5).map((entry) => (
              <ListRow
                key={entry.id}
                title={entry.subject_name || "Unrecognised document"}
                meta={[
                  entry.issuer_name,
                  timeAgo(entry.created_at),
                  entry.counts_against_quota ? "counted" : "free",
                ]
                  .filter(Boolean)
                  .join(" · ")}
                trailing={<OutcomeChip outcome={parseOutcome(entry.result)} />}
              />
            ))}
          </ListCard>
        )}
      </section>
    </div>
  );
}
