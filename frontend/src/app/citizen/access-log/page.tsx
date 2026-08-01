"use client";

import { useMemo, useState } from "react";

import { EmptyState, ListCard, ListRow } from "@/components/ui/dashboard";
import { ErrorState, filterClass, LoadingRows } from "@/components/ui/form";
import { OutcomeChip } from "@/components/verification/outcome-panel";
import { errorMessage } from "@/lib/api/errors";
import { useAccessLog } from "@/lib/api/hooks";
import { timeAgo } from "@/lib/api/types";
import { parseOutcome } from "@/lib/verification";

/**
 * The transparency log: who checked your credentials, and when.
 *
 * Unusual for a credential platform, and the feature most worth keeping.
 * Normally verification is invisible to its subject — an employer phones the
 * university and the graduate never learns it happened. Surfacing it inverts
 * that, and the transparency is itself a control: verifiers who know the subject
 * can see them are materially less likely to go fishing.
 */
export default function AccessLogPage() {
  const accessLog = useAccessLog();
  const [query, setQuery] = useState("");

  const entries = useMemo(() => {
    const all = accessLog.data ?? [];
    if (!query.trim()) return all;
    const needle = query.trim().toLowerCase();
    return all.filter(
      (entry) =>
        entry.verifier.toLowerCase().includes(needle) ||
        entry.credential.toLowerCase().includes(needle),
    );
  }, [accessLog.data, query]);

  return (
    <div className="mx-auto w-full max-w-3xl">
      <h1 className="text-lg font-semibold tracking-tight">Who checked your credentials</h1>
      <p className="mt-1.5 text-sm text-text-muted">
        Every verification of a credential belonging to you, newest first.
      </p>

      <div className="mt-4 flex flex-wrap gap-2">
        <input
          type="search"
          placeholder="Search by organisation or credential"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          className={`${filterClass} min-w-48 flex-1`}
          aria-label="Search the access log"
        />
      </div>

      <div className="mt-4">
        {accessLog.isPending ? (
          <LoadingRows rows={4} />
        ) : accessLog.isError ? (
          <ErrorState
            message={errorMessage(accessLog.error)}
            onRetry={() => void accessLog.refetch()}
          />
        ) : entries.length === 0 ? (
          <EmptyState
            icon="activity"
            title={query ? "No matches" : "Nobody has checked you yet"}
            description={
              query
                ? "Try a different search."
                : "When an employer verifies one of your credentials, it appears here — including anonymous QR scans."
            }
          />
        ) : (
          <ListCard>
            {entries.map((entry) => (
              <ListRow
                key={entry.id}
                title={entry.verifier}
                meta={`${entry.credential} · ${timeAgo(entry.created_at)}`}
                trailing={<OutcomeChip outcome={parseOutcome(entry.result)} />}
              />
            ))}
          </ListCard>
        )}
      </div>

      {/* Anonymous scans are listed but never located. Storing the IP of
          everyone who looked a citizen up would build a surveillance record of
          recruiters, which is a worse harm than the one it would solve. */}
      <p className="mt-3 text-xs text-text-subtle">
        Employers who look you up while signed in are named. Anonymous QR scans are shown
        without any location or device information — we do not keep it.
      </p>
    </div>
  );
}
