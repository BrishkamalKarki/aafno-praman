"use client";

import { BatchUpload } from "@/components/issuer/batch-upload";

/**
 * Bulk academic issuance.
 *
 * The template columns are the ones `apps/credentials/services.py::import_batch`
 * actually parses — `ACADEMIC_COLUMNS`, verbatim. A template that did not match
 * the parser would fail every row on the first upload, which is the single most
 * discouraging thing that can happen to an institution trying this out.
 */

const TEMPLATE = `full_name,email,registration_number,degree_title,major,level,graduation_date,graduation_date_bs,cgpa,percentage,honours
Ram Thapa,ram@example.com,TU-2078-CSIT-101,Bachelor of Science in Computer Science,Computer Science,BACHELORS,2026-05-20,2083-02-07,3.42,,
Sita Sharma,sita@example.com,TU-2078-CSIT-102,Bachelor of Science in Computer Science,Computer Science,BACHELORS,2026-05-20,2083-02-07,3.71,,Distinction`;

const REQUIRED = ["full_name", "email", "registration_number", "degree_title", "graduation_date"];

export default function BulkIssuePage() {
  return (
    <div className="mx-auto w-full max-w-3xl">
      <h1 className="text-lg font-semibold tracking-tight">Issue to a batch</h1>
      <p className="mt-1.5 text-sm text-text-muted">
        Upload a spreadsheet to issue a whole graduating batch. Valid rows are anchored together
        in a single transaction, so the institution pays for one write rather than one per
        graduate.
      </p>

      <BatchUpload
        recordType="ACADEMIC"
        template={TEMPLATE}
        requiredColumns={REQUIRED}
        backHref="/issuer"
        description="UTF-8 CSV. level must be one of SCHOOL, PLUS_TWO, DIPLOMA, BACHELORS, MASTERS, DOCTORATE."
      />
    </div>
  );
}
