"use client";

import { useState } from "react";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import { Card, CardBody } from "@/components/ui/card";
import { FileField, FormError, inputClass, labelClass, textareaClass } from "@/components/ui/form";
import { Icon } from "@/components/ui/icon";
import { errorMessage } from "@/lib/api/errors";
import { useIssueRecord } from "@/lib/api/hooks";
import type { CredentialRecord } from "@/lib/api/types";
import { useToast } from "@/lib/toast";

/**
 * A company confirming its own employee's history.
 *
 * Unlike `/employer/verify`, this never draws down the monthly quota on any
 * plan — see `lib/plans.ts` for why only verification volume is metered.
 *
 * The employee still has to confirm before anything is anchored. That is the
 * same consent gate academic credentials go through, and it applies here for the
 * same reason: a former employer publishing a permanent, public claim about
 * someone's departure without asking them is not a thing this platform does.
 */

const EMPLOYMENT_TYPES = [
  { value: "FULL_TIME", label: "Full-time" },
  { value: "PART_TIME", label: "Part-time" },
  { value: "CONTRACT", label: "Contract" },
  { value: "INTERNSHIP", label: "Internship" },
] as const;

const DEPARTURE = [
  { value: "RESIGNED", label: "Resigned" },
  { value: "CONTRACT_ENDED", label: "Contract ended" },
  { value: "TERMINATED", label: "Terminated" },
  { value: "RETIRED", label: "Retired" },
] as const;

const EMPTY = {
  subject_full_name: "",
  subject_email: "",
  job_title: "",
  department: "",
  employment_type: "FULL_TIME",
  start_date: "",
  end_date: "",
  departure_status: "RESIGNED",
  responsibilities: "",
};

export function ExperienceForm() {
  const issue = useIssueRecord("experience");
  const { notify } = useToast();

  const [values, setValues] = useState({ ...EMPTY });
  const [isCurrent, setIsCurrent] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<CredentialRecord | null>(null);

  function update(field: keyof typeof EMPTY, value: string) {
    setValues((current) => ({ ...current, [field]: value }));
  }

  function reset() {
    setValues({ ...EMPTY });
    setIsCurrent(false);
    setFile(null);
    setResult(null);
    setError(null);
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);

    try {
      const record = await issue.mutateAsync({
        subject_full_name: values.subject_full_name.trim(),
        subject_email: values.subject_email.trim().toLowerCase(),
        detail: {
          job_title: values.job_title.trim(),
          department: values.department.trim(),
          employment_type: values.employment_type,
          start_date: values.start_date,
          // Mirrors the database CHECK constraint: a current position has no
          // end date, and an ended one must have both a date and a status.
          ...(isCurrent
            ? { is_current: "true", departure_status: "CURRENT" }
            : { end_date: values.end_date, departure_status: values.departure_status }),
          responsibilities: values.responsibilities.trim(),
        },
        document: file,
      });
      setResult(record);
      notify("Confirmation sent to the employee.", "success");
    } catch (caught) {
      setError(errorMessage(caught, "Could not issue this experience letter."));
    }
  }

  if (result) {
    return (
      <Card raised className="mt-6">
        <CardBody className="flex flex-col items-center gap-2 pt-8 pb-8 text-center">
          <span className="flex size-11 items-center justify-center rounded-full bg-verified-surface text-verified">
            <Icon name="shield-check" size={20} />
          </span>
          <p className="text-base font-semibold tracking-tight">Confirmation sent</p>
          <p className="max-w-sm text-sm text-text-muted">
            {result.subject_full_name} has been emailed at {result.subject_email}. Nothing is
            anchored until they confirm it is theirs. This did not count against your plan.
          </p>

          <div className="mt-2 w-full max-w-sm rounded-[var(--radius-card)] border border-border bg-surface-muted p-4 text-left text-sm">
            <p className="text-xs font-medium text-text-subtle uppercase">
              Fingerprint they will be shown
            </p>
            <p className="mt-0.5 break-all font-mono text-xs">0x{result.record_hash}</p>
          </div>

          <div className="mt-2 flex gap-2">
            <Link href="/employer">
              <Button variant="secondary">Back to dashboard</Button>
            </Link>
            <Button variant="ghost" onClick={reset}>
              Issue another
            </Button>
          </div>
        </CardBody>
      </Card>
    );
  }

  return (
    <Card className="mt-6">
      <CardBody className="pt-5">
        <form onSubmit={handleSubmit} className="space-y-5">
          <FormError message={error} />

          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label htmlFor="subject_full_name" className={labelClass}>
                Employee full name
              </label>
              <input
                id="subject_full_name"
                required
                value={values.subject_full_name}
                onChange={(event) => update("subject_full_name", event.target.value)}
                className={inputClass}
              />
            </div>

            <div>
              <label htmlFor="subject_email" className={labelClass}>
                Employee email
              </label>
              <input
                id="subject_email"
                type="email"
                required
                value={values.subject_email}
                onChange={(event) => update("subject_email", event.target.value)}
                className={inputClass}
              />
            </div>

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
                Still employed here
              </label>
            </div>

            {!isCurrent && (
              <div>
                <label htmlFor="departure_status" className={labelClass}>
                  How the employment ended
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
                Responsibilities <span className="font-normal text-text-subtle">(optional)</span>
              </label>
              <textarea
                id="responsibilities"
                rows={2}
                value={values.responsibilities}
                onChange={(event) => update("responsibilities", event.target.value)}
                className={textareaClass}
              />
            </div>

            <div className="sm:col-span-2">
              <FileField
                id="document"
                label="Signed letter"
                optional
                accept=".pdf,.png,.jpg,.jpeg"
                file={file}
                onSelect={setFile}
                hint="PDF, PNG or JPEG. Attaching it is what lets anyone later verify by uploading the same file."
              />
            </div>
          </div>

          <div className="flex items-start gap-2 rounded-[var(--radius-card)] border border-border bg-surface-muted px-4 py-3 text-sm text-text-muted">
            <Icon name="activity" size={16} className="mt-0.5 shrink-0 text-brand" />
            <span>
              Network fee covered by Aafno Praman, signed by your organisation&apos;s platform-held
              key. No wallet connection needed, and issuing is never metered.
            </span>
          </div>

          <Button type="submit" size="lg" loading={issue.isPending}>
            Issue experience letter
          </Button>
        </form>
      </CardBody>
    </Card>
  );
}
