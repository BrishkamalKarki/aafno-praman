"use client";

import { useMemo, useState } from "react";

import { EmptyState, ListCard, ListRow } from "@/components/ui/dashboard";
import { ErrorState, filterClass, LoadingRows } from "@/components/ui/form";
import { OutcomeChip } from "@/components/verification/outcome-panel";
import { errorMessage } from "@/lib/api/errors";
import { useVerificationHistory } from "@/lib/api/hooks";
import { timeAgo } from "@/lib/api/types";
import { parseOutcome, VERIFICATION_OUTCOMES, type VerificationOutcome } from "@/lib/verification";

/**
 * Every document this organisation has checked.
 *
 * The outcome filter is server-side (`filterset_fields = ["result"]`); the free
 * text box narrows what came back, because there is no search index over
 * verification logs and adding one for a demo would be premature.
 */
export default function EmployerHistoryPage() {
  const [outcome, setOutcome] = useState<VerificationOutcome | "">("");
  const [query, setQuery] = useState("");

  const history = useVerificationHistory(outcome || undefined);

  const entries = useMemo(() => {
    const all = history.data ?? [];
    if (!query.trim()) return all;
    const needle = query.trim().toLowerCase();
    return all.filter(
      (entry) =>
        (entry.subject_name ?? "").toLowerCase().includes(needle) ||
        (entry.issuer_name ?? "").toLowerCase().includes(needle) ||
        entry.lookup_reference.toLowerCase().includes(needle),
    );
  }, [history.data, query]);

  return (
    <div className="mx-auto w-full max-w-3xl">
      <h1 className="text-lg font-semibold tracking-tight">Verification history</h1>
      <p className="mt-1.5 text-sm text-text-muted">
        Every document your team has checked, and whether it counted against your allowance.
      </p>

      <div className="mt-4 flex flex-wrap gap-2">
        <input
          type="search"
          placeholder="Search by candidate, issuer, or reference"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          className={`${filterClass} min-w-48 flex-1`}
          aria-label="Search verification history"
        />
        <select
          value={outcome}
          onChange={(event) => setOutcome(event.target.value as VerificationOutcome | "")}
          className={filterClass}
          aria-label="Filter by outcome"
        >
          <option value="">All outcomes</option>
          {VERIFICATION_OUTCOMES.map((entry) => (
            <option key={entry} value={entry}>
              {entry.replace(/_/g, " ").toLowerCase()}
            </option>
          ))}
        </select>
      </div>

      <div className="mt-4">
        {history.isPending ? (
          <LoadingRows rows={4} />
        ) : history.isError ? (
          <ErrorState
            message={errorMessage(history.error)}
            onRetry={() => void history.refetch()}
          />
        ) : entries.length === 0 ? (
          <EmptyState
            icon="search"
            title={query || outcome ? "No matches" : "Nothing checked yet"}
            description={
              query || outcome
                ? "Try a different search or outcome filter."
                : "Upload a candidate's certificate on the Check validity page and the result is recorded here."
            }
          />
        ) : (
          <ListCard>
            {entries.map((entry) => (
              <ListRow
                key={entry.id}
                title={entry.subject_name || "Unrecognised document"}
                subtitle={entry.lookup_reference}
                meta={[
                  entry.issuer_name,
                  timeAgo(entry.created_at),
                  // Whether a check was metered is the thing an employer
                  // disputes at the end of the month, so it is on every row
                  // rather than buried in a billing summary.
                  entry.counts_against_quota ? "counted against your plan" : "free",
                ]
                  .filter(Boolean)
                  .join(" · ")}
                trailing={<OutcomeChip outcome={parseOutcome(entry.result)} />}
              />
            ))}
          </ListCard>
        )}
      </div>
    </div>
  );
}
