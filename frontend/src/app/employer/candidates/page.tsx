"use client";

import { useState } from "react";

import { Card, CardBody } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/dashboard";
import { ErrorState, filterClass, LoadingRows } from "@/components/ui/form";
import { Icon } from "@/components/ui/icon";
import { errorMessage } from "@/lib/api/errors";
import { useCandidates, type Candidate } from "@/lib/api/hooks";

/**
 * Candidates who have chosen to be findable.
 *
 * Restricted to seekers who explicitly opted in, and the opt-in is what makes
 * this defensible at all: without it the endpoint would be a scraper for every
 * citizen's education history, which is a considerably worse outcome than the
 * fraud the platform sets out to stop.
 *
 * This screen existed nowhere until now, which made the "let employers find me"
 * switch on the citizen's own profile a control with nothing behind it — a
 * setting that consented to something that could not happen.
 *
 * No contact details are shown, because the API does not return any. An
 * employer sees verified qualifications and reaches out through the platform;
 * they do not get a mailing list.
 */

const LEVEL_LABELS: Record<string, string> = {
  DOCTORATE: "Doctorate",
  MASTERS: "Masters",
  BACHELORS: "Bachelors",
  DIPLOMA: "Diploma",
  PLUS_TWO: "Higher secondary",
  SCHOOL: "School",
};

export default function CandidatesPage() {
  const [input, setInput] = useState("");
  const [query, setQuery] = useState("");

  const candidates = useCandidates(query);

  return (
    <div className="mx-auto w-full max-w-3xl">
      <h1 className="text-lg font-semibold tracking-tight">Find candidates</h1>
      <p className="mt-1.5 max-w-xl text-sm text-text-muted">
        People who have chosen to be findable, with qualifications already verified on the
        ledger. Searching here is free and never counts against your plan.
      </p>

      <form
        className="mt-4 flex flex-wrap gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          setQuery(input);
        }}
      >
        <input
          type="search"
          placeholder="Search by name, headline, or degree"
          value={input}
          onChange={(event) => setInput(event.target.value)}
          className={`${filterClass} min-w-48 flex-1`}
          aria-label="Search candidates"
        />
        <button
          type="submit"
          className="inline-flex h-10 items-center gap-1.5 rounded-[var(--radius-control)] bg-text px-4 text-sm font-medium text-text-inverted hover:opacity-90"
        >
          <Icon name="search" size={15} />
          Search
        </button>
      </form>

      <div className="mt-4 space-y-3">
        {candidates.isPending ? (
          <LoadingRows rows={3} />
        ) : candidates.isError ? (
          <ErrorState
            message={errorMessage(candidates.error)}
            onRetry={() => void candidates.refetch()}
          />
        ) : (candidates.data?.length ?? 0) === 0 ? (
          <EmptyState
            icon="user"
            title={query ? "No matches" : "Nobody is findable yet"}
            description={
              query
                ? "Try a different search."
                : "Candidates appear here only after switching on discoverability in their own account, which is off by default."
            }
          />
        ) : (
          candidates.data?.map((candidate) => (
            <CandidateCard key={candidate.id} candidate={candidate} />
          ))
        )}
      </div>

      <p className="mt-4 text-xs text-text-subtle">
        Contact details are never shown here — not by omission, but because the platform does not
        return them. Ask a candidate for their credentials through a share link.
      </p>
    </div>
  );
}

function CandidateCard({ candidate }: { candidate: Candidate }) {
  return (
    <Card>
      <CardBody className="pt-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="text-base font-semibold tracking-tight">{candidate.full_name}</p>
            {candidate.headline && (
              <p className="mt-0.5 text-sm text-text-muted">{candidate.headline}</p>
            )}
          </div>
          {candidate.highest_qualification && (
            <span
              className="inline-flex shrink-0 items-center rounded-full border px-2.5 py-1 text-xs font-medium"
              style={{
                color: "var(--color-verified)",
                backgroundColor: "var(--color-verified-surface)",
                borderColor: "var(--color-verified-border)",
              }}
            >
              {LEVEL_LABELS[candidate.highest_qualification] ?? candidate.highest_qualification}
            </span>
          )}
        </div>

        <p className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-text-muted">
          <span className="inline-flex items-center gap-1.5">
            <Icon name="shield-check" size={14} className="shrink-0 text-brand" />
            {candidate.verified_academic_count} verified academic
          </span>
          <span className="inline-flex items-center gap-1.5">
            <Icon name="building" size={14} className="shrink-0 text-brand" />
            {candidate.verified_experience_count} verified employment
          </span>
        </p>
      </CardBody>
    </Card>
  );
}
