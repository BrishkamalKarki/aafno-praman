"use client";

import { useState } from "react";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import { Card, CardBody } from "@/components/ui/card";
import { EmptyState, ListCard, ListRow, StatusPill } from "@/components/ui/dashboard";
import {
  FormError,
  inputClass,
  labelClass,
  LoadingRows,
  textareaClass,
} from "@/components/ui/form";
import { Icon } from "@/components/ui/icon";
import { errorMessage } from "@/lib/api/errors";
import { useClaimExperience, useOrganizationDirectory, usePassport } from "@/lib/api/hooks";
import { formatDate, pillFor, recordTitle, timeAgo } from "@/lib/api/types";
import { useToast } from "@/lib/toast";

/**
 * Log employment for a past employer to confirm.
 *
 * The other direction of issuance, and the half that was missing. The employer
 * console already had a review inbox, but nothing in the product could put a
 * claim into it — so a candidate whose old company never issued them anything
 * had no way to get that job on their record at all.
 *
 * Nothing here is hashed and nothing reaches the chain. An unendorsed claim is
 * an assertion by the person making it; anchoring one would let anybody write
 * self-attested "verified" employment onto a public ledger, which is precisely
 * the fraud this platform exists to prevent. It becomes a credential only when
 * someone at the named company confirms it.
 */

const EMPLOYMENT_TYPES = [
  { value: "FULL_TIME", label: "Full-time" },
  { value: "PART_TIME", label: "Part-time" },
  { value: "CONTRACT", label: "Contract" },
  { value: "INTERNSHIP", label: "Internship" },
] as const;

const DEPARTURE = [
  { value: "RESIGNED", label: "I resigned" },
  { value: "CONTRACT_ENDED", label: "The contract ended" },
  { value: "TERMINATED", label: "I was let go" },
  { value: "RETIRED", label: "I retired" },
] as const;

const EMPTY = {
  employer: "",
  job_title: "",
  department: "",
  employment_type: "FULL_TIME",
  start_date: "",
  end_date: "",
  departure_status: "RESIGNED",
  responsibilities: "",
};

export default function NewClaimPage() {
  const employers = useOrganizationDirectory("EMPLOYER");
  const passport = usePassport();
  const claim = useClaimExperience();
  const { notify } = useToast();

  const [values, setValues] = useState({ ...EMPTY });
  const [isCurrent, setIsCurrent] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  function update(field: keyof typeof EMPTY, value: string) {
    setValues((current) => ({ ...current, [field]: value }));
  }

  // Claims already submitted, so somebody does not file the same job twice
  // while waiting — the backend would reject the duplicate anyway, but finding
  // that out from a 409 is a worse way to learn it.
  const pending = (passport.data?.records ?? []).filter(
    (record) => record.issuance_mode === "SEEKER_CLAIM",
  );

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);

    try {
      await claim.mutateAsync({
        employer: values.employer,
        detail: {
          job_title: values.job_title.trim(),
          department: values.department.trim(),
          employment_type: values.employment_type,
          start_date: values.start_date,
          // Mirrors the database CHECK constraint: a current position carries
          // no end date, and an ended one needs both a date and a status.
          ...(isCurrent
            ? { is_current: true, departure_status: "CURRENT" }
            : { end_date: values.end_date, departure_status: values.departure_status }),
          responsibilities: values.responsibilities.trim(),
        },
      });
      setValues({ ...EMPTY });
      setIsCurrent(false);
      setDone(true);
      notify("Sent to the employer to confirm.", "success");
    } catch (caught) {
      setError(errorMessage(caught, "Could not submit this claim."));
    }
  }

  if (done) {
    return (
      <div className="mx-auto w-full max-w-xl">
        <Card raised>
          <CardBody className="flex flex-col items-center gap-3 pt-8 pb-8 text-center">
            <span className="flex size-11 items-center justify-center rounded-full bg-verified-surface text-verified">
              <Icon name="inbox" size={20} />
            </span>
            <p className="text-base font-semibold tracking-tight">Sent for confirmation</p>
            <p className="max-w-sm text-sm text-text-muted">
              It is now in that company&apos;s review queue. Nothing is published, and nothing
              reaches the ledger, until someone there confirms it — if they dispute it, you will
              be told why.
            </p>
            <div className="mt-2 flex gap-2">
              <Link href="/citizen/credentials">
                <Button variant="secondary">See my credentials</Button>
              </Link>
              <Button variant="ghost" onClick={() => setDone(false)}>
                Log another job
              </Button>
            </div>
          </CardBody>
        </Card>
      </div>
    );
  }

  return (
    <div className="mx-auto w-full max-w-2xl">
      <h1 className="text-lg font-semibold tracking-tight">Log a past job</h1>
      <p className="mt-1.5 text-sm text-text-muted">
        For work an employer never issued a letter for. You describe it, they confirm it, and
        only then does it become a verifiable credential.
      </p>

      <Card className="mt-6">
        <CardBody className="pt-5">
          <form onSubmit={handleSubmit} className="space-y-5">
            <FormError message={error} />

            <div>
              <label htmlFor="employer" className={labelClass}>
                Which company
              </label>
              <select
                id="employer"
                required
                value={values.employer}
                onChange={(event) => update("employer", event.target.value)}
                className={inputClass}
                disabled={employers.isPending}
              >
                <option value="" disabled>
                  {employers.isPending ? "Loading employers…" : "Select…"}
                </option>
                {employers.data?.map((employer) => (
                  <option key={employer.id} value={employer.id}>
                    {employer.legal_name}
                  </option>
                ))}
              </select>
              {/* Free text is not offered on purpose: a claim against a company
                  with no account here is one nobody can dispute. */}
              <p className="mt-1 text-xs text-text-subtle">
                Only companies registered on Aafno Praman can confirm a claim. If yours is not
                listed, ask them to register.
              </p>
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <label htmlFor="job_title" className={labelClass}>
                  Job title
                </label>
                <input
                  id="job_title"
                  required
                  placeholder="e.g. Software Engineer"
                  value={values.job_title}
                  onChange={(event) => update("job_title", event.target.value)}
                  className={inputClass}
                />
              </div>

              <div>
                <label htmlFor="employment_type" className={labelClass}>
                  Employment type
                </label>
                <select
                  id="employment_type"
                  required
                  value={values.employment_type}
                  onChange={(event) => update("employment_type", event.target.value)}
                  className={inputClass}
                >
                  {EMPLOYMENT_TYPES.map((type) => (
                    <option key={type.value} value={type.value}>
                      {type.label}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label htmlFor="department" className={labelClass}>
                  Department <span className="font-normal text-text-subtle">(optional)</span>
                </label>
                <input
                  id="department"
                  value={values.department}
                  onChange={(event) => update("department", event.target.value)}
                  className={inputClass}
                />
              </div>

              <div>
                <label htmlFor="start_date" className={labelClass}>
                  Start date
                </label>
                <input
                  id="start_date"
                  type="date"
                  required
                  value={values.start_date}
                  onChange={(event) => update("start_date", event.target.value)}
                  className={inputClass}
                />
              </div>

              <div>
                <label htmlFor="end_date" className={labelClass}>
                  End date
                </label>
                <input
                  id="end_date"
                  type="date"
                  required={!isCurrent}
                  disabled={isCurrent}
                  value={isCurrent ? "" : values.end_date}
                  onChange={(event) => update("end_date", event.target.value)}
                  className={inputClass}
                />
              </div>

              <div className="flex items-end pb-2.5">
                <label className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={isCurrent}
                    onChange={(event) => setIsCurrent(event.target.checked)}
                    className="size-4"
                  />
                  I still work here
                </label>
              </div>

              {!isCurrent && (
                <div className="sm:col-span-2">
                  <label htmlFor="departure_status" className={labelClass}>
                    How it ended
                  </label>
                  <select
                    id="departure_status"
                    required
                    value={values.departure_status}
                    onChange={(event) => update("departure_status", event.target.value)}
                    className={inputClass}
                  >
                    {DEPARTURE.map((status) => (
                      <option key={status.value} value={status.value}>
                        {status.label}
                      </option>
                    ))}
                  </select>
                </div>
              )}

              <div className="sm:col-span-2">
                <label htmlFor="responsibilities" className={labelClass}>
                  What you did <span className="font-normal text-text-subtle">(optional)</span>
                </label>
                <textarea
                  id="responsibilities"
                  rows={2}
                  value={values.responsibilities}
                  onChange={(event) => update("responsibilities", event.target.value)}
                  className={textareaClass}
                />
              </div>
            </div>

            <Button type="submit" size="lg" loading={claim.isPending}>
              Send to the employer
            </Button>
          </form>
        </CardBody>
      </Card>

      <section aria-labelledby="submitted" className="mt-8">
        <h2 id="submitted" className="mb-3 text-sm font-semibold tracking-tight">
          Jobs you have logged
        </h2>

        {passport.isPending ? (
          <LoadingRows rows={2} />
        ) : pending.length === 0 ? (
          <EmptyState
            icon="inbox"
            title="Nothing logged yet"
            description="Anything you submit above appears here with what the employer decided."
          />
        ) : (
          <ListCard>
            {pending.map((record) => (
              <ListRow
                key={record.id}
                title={recordTitle(record)}
                meta={[
                  record.issuer_name,
                  record.detail.start_date ? formatDate(record.detail.start_date) : null,
                  `submitted ${timeAgo(record.created_at)}`,
                  // The reason a claim was rejected is the whole point of
                  // requiring one — it is how an honest mistake gets fixed.
                  record.review_note || null,
                ]
                  .filter(Boolean)
                  .join(" · ")}
                trailing={<StatusPill state={pillFor(record.status)} />}
              />
            ))}
          </ListCard>
        )}
      </section>
    </div>
  );
}
