"use client";

import { useState } from "react";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import { Card, CardBody } from "@/components/ui/card";
import { FileField, FormError, inputClass, labelClass } from "@/components/ui/form";
import { Icon } from "@/components/ui/icon";
import { errorMessage } from "@/lib/api/errors";
import { useIssueRecord } from "@/lib/api/hooks";
import type { CredentialRecord } from "@/lib/api/types";
import { useToast } from "@/lib/toast";

/**
 * Issue one academic credential.
 *
 * The button used to say "Sign & anchor" and show a gas estimate. Both were
 * wrong about this system: issuance does not reach the chain at all. It creates
 * an **offer**, emails the graduate, and only their confirmation moves it into
 * the anchor queue — so the success screen says what actually happened, which is
 * that somebody has been asked.
 *
 * The certificate file is optional and never leaves the issuer's control as
 * anything but a hash. Attaching it is what later lets an employer verify by
 * uploading the same PDF.
 */

const LEVELS = [
  { value: "SCHOOL", label: "School (SEE)" },
  { value: "PLUS_TWO", label: "Higher secondary (+2)" },
  { value: "DIPLOMA", label: "Diploma" },
  { value: "BACHELORS", label: "Bachelors" },
  { value: "MASTERS", label: "Masters" },
  { value: "DOCTORATE", label: "Doctorate" },
] as const;

const EMPTY = {
  subject_full_name: "",
  subject_email: "",
  national_id: "",
  registration_number: "",
  degree_title: "",
  major: "",
  level: "BACHELORS",
  graduation_date: "",
  graduation_date_bs: "",
  cgpa: "",
  percentage: "",
  honours: "",
};

export default function IssueSinglePage() {
  const issue = useIssueRecord("academic");
  const { notify } = useToast();

  const [values, setValues] = useState({ ...EMPTY });
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<CredentialRecord | null>(null);

  function update(field: keyof typeof EMPTY, value: string) {
    setValues((current) => ({ ...current, [field]: value }));
  }

  function reset() {
    setValues({ ...EMPTY });
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
        national_id: values.national_id.trim(),
        detail: {
          registration_number: values.registration_number.trim(),
          degree_title: values.degree_title.trim(),
          major: values.major.trim(),
          level: values.level,
          graduation_date: values.graduation_date,
          graduation_date_bs: values.graduation_date_bs.trim(),
          cgpa: values.cgpa.trim(),
          percentage: values.percentage.trim(),
          honours: values.honours.trim(),
        },
        document: file,
      });
      setResult(record);
      notify("Confirmation sent to the graduate.", "success");
    } catch (caught) {
      setError(errorMessage(caught, "Could not issue this credential."));
    }
  }

  if (result) {
    return (
      <div className="mx-auto w-full max-w-xl">
        <Card raised>
          <CardBody className="flex flex-col items-center gap-3 pt-8 pb-8 text-center">
            <span className="flex size-11 items-center justify-center rounded-full bg-verified-surface text-verified">
              <Icon name="shield-check" size={20} />
            </span>
            <p className="text-base font-semibold tracking-tight">Sent for confirmation</p>
            <p className="max-w-sm text-sm text-text-muted">
              {result.subject_full_name} has been emailed at {result.subject_email}. Nothing is
              written to the ledger until they confirm it is theirs.
            </p>

            <div className="mt-2 w-full rounded-[var(--radius-card)] border border-border bg-surface-muted p-4 text-left text-sm">
              <p className="text-xs font-medium text-text-subtle uppercase">
                Fingerprint they will be shown
              </p>
              <p className="mt-0.5 break-all font-mono text-xs">0x{result.record_hash}</p>
              <p className="mt-3 text-xs font-medium text-text-subtle uppercase">Ledger status</p>
              <p className="mt-0.5">
                Awaiting the holder&apos;s confirmation — no transaction yet, by design.
              </p>
            </div>

            <div className="mt-2 flex gap-2">
              <Link href="/issuer">
                <Button variant="secondary">Back to dashboard</Button>
              </Link>
              <Button variant="ghost" onClick={reset}>
                Issue another
              </Button>
            </div>
          </CardBody>
        </Card>
      </div>
    );
  }

  return (
    <div className="mx-auto w-full max-w-2xl">
      <h1 className="text-lg font-semibold tracking-tight">Issue a credential</h1>
      <p className="mt-1.5 text-sm text-text-muted">
        One recipient, by email. They confirm before anything is anchored.
      </p>

      <Card className="mt-6">
        <CardBody className="pt-5">
          <form onSubmit={handleSubmit} className="space-y-5">
            <FormError message={error} />

            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <label className={labelClass} htmlFor="subject_full_name">
                  Recipient full name
                </label>
                <input
                  id="subject_full_name"
                  required
                  className={inputClass}
                  value={values.subject_full_name}
                  onChange={(event) => update("subject_full_name", event.target.value)}
                />
              </div>

              <div>
                <label className={labelClass} htmlFor="subject_email">
                  Recipient email
                </label>
                <input
                  id="subject_email"
                  type="email"
                  required
                  className={inputClass}
                  value={values.subject_email}
                  onChange={(event) => update("subject_email", event.target.value)}
                />
              </div>

              <div>
                <label className={labelClass} htmlFor="registration_number">
                  Registration number
                </label>
                <input
                  id="registration_number"
                  required
                  placeholder="e.g. TU-2078-CSIT-041"
                  className={inputClass}
                  value={values.registration_number}
                  onChange={(event) => update("registration_number", event.target.value)}
                />
              </div>

              <div>
                <label className={labelClass} htmlFor="level">
                  Level
                </label>
                <select
                  id="level"
                  required
                  className={inputClass}
                  value={values.level}
                  onChange={(event) => update("level", event.target.value)}
                >
                  {LEVELS.map((level) => (
                    <option key={level.value} value={level.value}>
                      {level.label}
                    </option>
                  ))}
                </select>
              </div>

              <div className="sm:col-span-2">
                <label className={labelClass} htmlFor="degree_title">
                  Degree title
                </label>
                <input
                  id="degree_title"
                  required
                  placeholder="e.g. Bachelor of Science in Computer Science"
                  className={inputClass}
                  value={values.degree_title}
                  onChange={(event) => update("degree_title", event.target.value)}
                />
              </div>

              <div>
                <label className={labelClass} htmlFor="major">
                  Major <span className="font-normal text-text-subtle">(optional)</span>
                </label>
                <input
                  id="major"
                  className={inputClass}
                  value={values.major}
                  onChange={(event) => update("major", event.target.value)}
                />
              </div>

              <div>
                <label className={labelClass} htmlFor="graduation_date">
                  Graduation date (AD)
                </label>
                <input
                  id="graduation_date"
                  type="date"
                  required
                  className={inputClass}
                  value={values.graduation_date}
                  onChange={(event) => update("graduation_date", event.target.value)}
                />
              </div>

              <div>
                <label className={labelClass} htmlFor="graduation_date_bs">
                  Graduation date (BS){" "}
                  <span className="font-normal text-text-subtle">(optional)</span>
                </label>
                <input
                  id="graduation_date_bs"
                  placeholder="2083-03-01"
                  className={inputClass}
                  value={values.graduation_date_bs}
                  onChange={(event) => update("graduation_date_bs", event.target.value)}
                />
              </div>

              <div>
                <label className={labelClass} htmlFor="cgpa">
                  CGPA <span className="font-normal text-text-subtle">(optional, 0–4)</span>
                </label>
                <input
                  id="cgpa"
                  inputMode="decimal"
                  className={inputClass}
                  value={values.cgpa}
                  onChange={(event) => update("cgpa", event.target.value)}
                />
              </div>

              <div>
                <label className={labelClass} htmlFor="percentage">
                  Percentage{" "}
                  <span className="font-normal text-text-subtle">(optional)</span>
                </label>
                <input
                  id="percentage"
                  inputMode="decimal"
                  className={inputClass}
                  value={values.percentage}
                  onChange={(event) => update("percentage", event.target.value)}
                />
              </div>

              <div className="sm:col-span-2">
                <label className={labelClass} htmlFor="national_id">
                  Citizenship number{" "}
                  <span className="font-normal text-text-subtle">(optional)</span>
                </label>
                <input
                  id="national_id"
                  className={inputClass}
                  value={values.national_id}
                  onChange={(event) => update("national_id", event.target.value)}
                  autoComplete="off"
                />
                {/* Supplying this is the institution vouching for a number it
                    already holds on file — it is what later lets a verifier be
                    told whether a genuine certificate belongs to the person
                    they named. Omitting it is fine; the credential is still
                    fully verifiable. */}
                <p className="mt-1 text-xs text-text-subtle">
                  Only if your records already hold it. Supplying it lets employers confirm the
                  certificate belongs to the person presenting it. It is never published.
                </p>
              </div>

              <div className="sm:col-span-2">
                <FileField
                  id="document"
                  label="Certificate file"
                  optional
                  accept=".pdf,.png,.jpg,.jpeg"
                  file={file}
                  onSelect={setFile}
                  hint="PDF, PNG or JPEG. Attaching it is what lets an employer later verify by uploading the same file."
                />
              </div>
            </div>

            <div className="rounded-[var(--radius-card)] border border-border bg-surface-muted px-4 py-3 text-sm text-text-muted">
              <p className="flex items-start gap-2">
                <Icon name="shield-check" size={16} className="mt-0.5 shrink-0 text-brand" />
                <span>
                  Nothing reaches the ledger yet. The graduate is emailed the exact fingerprint
                  and confirms before it is anchored — and your signing key, held by the
                  platform, submits the transaction. No wallet, no gas.
                </span>
              </p>
            </div>

            <Button type="submit" size="lg" loading={issue.isPending}>
              Send for confirmation
            </Button>
          </form>
        </CardBody>
      </Card>
    </div>
  );
}
