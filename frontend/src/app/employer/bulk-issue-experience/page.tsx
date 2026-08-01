"use client";

import { BatchUpload } from "@/components/issuer/batch-upload";

/**
 * Bulk experience-letter issuance.
 *
 * Template columns are `EXPERIENCE_COLUMNS` from
 * `apps/credentials/services.py::import_batch`, verbatim — a template the parser
 * disagrees with would fail every row on the first try.
 *
 * Leaving `end_date` blank (or writing `present`) marks the row as a current
 * position, which is what the parser does with it, and is why the second sample
 * row has an empty trailing field rather than a placeholder date.
 */

const TEMPLATE = `full_name,email,job_title,department,employment_type,start_date,end_date,departure_status,responsibilities
Anish Shrestha,anish@example.com,Backend Engineer,Engineering,FULL_TIME,2023-01-10,2025-06-30,RESIGNED,Django services and CI pipelines
Prakriti Koirala,prakriti@example.com,Product Designer,Design,FULL_TIME,2022-08-01,,CURRENT,Design system and research`;

const REQUIRED = ["full_name", "email", "job_title", "start_date"];

export default function BulkIssueExperiencePage() {
  return (
    <div className="mx-auto w-full max-w-3xl">
      <h1 className="text-lg font-semibold tracking-tight">Bulk issue experience letters</h1>
      <p className="mt-1.5 text-sm text-text-muted">
        Upload a spreadsheet to issue a whole team&apos;s experience letters at once. Free on
        every plan, same as issuing one at a time.
      </p>

      <BatchUpload
        recordType="EXPERIENCE"
        template={TEMPLATE}
        requiredColumns={REQUIRED}
        backHref="/employer"
        description="UTF-8 CSV. Leave end_date blank for someone still employed, and set departure_status to CURRENT for that row."
      />
    </div>
  );
}
