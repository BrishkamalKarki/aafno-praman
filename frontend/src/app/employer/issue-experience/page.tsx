"use client";

import { ExperienceForm } from "./experience-form";

/**
 * Issue a single experience letter.
 *
 * No wallet connect and no quota. Employer issuance is signed by the company's
 * custodial key server-side, and it is never metered on any plan: a company
 * confirming its own employee's history is supply, not consumption. Only
 * checking other people's documents draws from the allowance.
 */
export default function IssueExperiencePage() {
  return (
    <div className="mx-auto w-full max-w-2xl">
      <h1 className="text-lg font-semibold tracking-tight">Issue an experience letter</h1>
      <p className="mt-1.5 text-sm text-text-muted">
        Confirms an employee&apos;s own work history. Free on every plan, and never counts
        against your verification quota.
      </p>

      <ExperienceForm />
    </div>
  );
}
