"use client";

import { useState } from "react";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import { Card, CardBody } from "@/components/ui/card";
import { FileField, FormError } from "@/components/ui/form";
import { Icon } from "@/components/ui/icon";
import { TxLink } from "@/components/ui/tx-link";
import { downloadTextFile, parseCsv, validateRow } from "@/lib/csv";
import { errorMessage } from "@/lib/api/errors";
import { useUploadBatch } from "@/lib/api/hooks";
import type { IssuanceBatch } from "@/lib/api/types";
import { useToast } from "@/lib/toast";

/**
 * CSV batch issuance, shared by the institution and employer consoles.
 *
 * ## Why the browser previews before uploading
 *
 * The server is the authority on what is valid — it re-parses every row and
 * records each rejection with its original content. The client-side pass is a
 * courtesy: a registrar who mistyped a header should find out before sending
 * four hundred rows, not after.
 *
 * ## Why every rejected row is shown afterwards
 *
 * Silently dropping a bad row leaves a graduate with no credential and nobody
 * aware of it — the worst failure this system could have. So the result panel
 * lists every rejection with the row number and the reason, and stays on screen
 * until dismissed.
 */
export function BatchUpload({
  recordType,
  template,
  requiredColumns,
  backHref,
  description,
}: {
  recordType: "ACADEMIC" | "EXPERIENCE";
  template: string;
  requiredColumns: readonly string[];
  backHref: string;
  description: string;
}) {
  const upload = useUploadBatch();
  const { notify } = useToast();

  const [file, setFile] = useState<File | null>(null);
  const [rows, setRows] = useState<Array<{ row: Record<string, string>; errors: string[] }>>([]);
  const [error, setError] = useState<string | null>(null);
  const [batch, setBatch] = useState<IssuanceBatch | null>(null);

  async function handleFile(selected: File | null) {
    setBatch(null);
    setError(null);
    setFile(selected);

    if (!selected) {
      setRows([]);
      return;
    }
    const text = await selected.text();
    setRows(parseCsv(text).map((row) => ({ row, errors: validateRow(row, requiredColumns) })));
  }

  const validCount = rows.filter((entry) => entry.errors.length === 0).length;
  const invalidCount = rows.length - validCount;

  async function handleSubmit() {
    if (!file) return;
    setError(null);
    try {
      const result = await upload.mutateAsync({ file, record_type: recordType });
      setBatch(result);
      notify(
        `${result.accepted_rows} of ${result.total_rows} rows accepted.`,
        result.rejected_rows > 0 ? "info" : "success",
      );
    } catch (caught) {
      setError(errorMessage(caught, "The batch could not be uploaded."));
    }
  }

  const nameColumn = recordType === "ACADEMIC" ? "degree_title" : "job_title";

  return (
    <>
      <div className="mt-4 flex flex-wrap gap-2">
        <Button
          variant="secondary"
          onClick={() => downloadTextFile(`aafno-praman-${recordType.toLowerCase()}-template.csv`, template)}
        >
          <Icon name="download" size={16} />
          Download CSV template
        </Button>
      </div>

      <Card className="mt-4">
        <CardBody className="pt-5">
          <FileField
            id="csv"
            label="Upload completed spreadsheet"
            accept=".csv,text/csv"
            file={file}
            onSelect={(selected) => void handleFile(selected)}
            hint={description}
          />

          {error && (
            <div className="mt-4">
              <FormError message={error} />
            </div>
          )}

          {file && rows.length === 0 && !batch && (
            <p className="mt-3 text-sm" style={{ color: "var(--color-danger)" }}>
              No usable rows found in {file.name}. Check it matches the template columns.
            </p>
          )}

          {rows.length > 0 && !batch && (
            <>
              <div className="mt-4 flex flex-wrap gap-4 text-sm">
                <p>
                  <span className="font-semibold text-verified">{validCount}</span> ready
                </p>
                {invalidCount > 0 && (
                  <p>
                    <span className="font-semibold text-tampered">{invalidCount}</span> need fixing
                  </p>
                )}
              </div>

              <div className="mt-3 max-h-80 overflow-auto rounded-[var(--radius-card)] border border-border">
                <table className="w-full text-left text-sm">
                  <thead className="bg-surface-muted text-xs text-text-subtle">
                    <tr>
                      <th className="px-3 py-2 font-medium">Name</th>
                      <th className="px-3 py-2 font-medium">Email</th>
                      <th className="px-3 py-2 font-medium">Credential</th>
                      <th className="px-3 py-2 font-medium">Status</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {rows.map((entry, index) => (
                      <tr
                        key={index}
                        className={entry.errors.length ? "bg-tampered-surface/40" : undefined}
                      >
                        <td className="px-3 py-2">{entry.row.full_name || "—"}</td>
                        <td className="px-3 py-2 font-mono text-xs">{entry.row.email || "—"}</td>
                        <td className="px-3 py-2">{entry.row[nameColumn] || "—"}</td>
                        <td className="px-3 py-2 text-xs">
                          {entry.errors.length ? entry.errors.join(", ") : "Ready"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <Button
                className="mt-4"
                size="lg"
                loading={upload.isPending}
                disabled={validCount === 0}
                onClick={() => void handleSubmit()}
              >
                Upload {validCount} row{validCount === 1 ? "" : "s"}
              </Button>
              <p className="mt-2 text-xs text-text-subtle">
                The server re-checks every row. Anything it rejects is listed back to you with
                the reason.
              </p>
            </>
          )}

          {batch && <BatchResult batch={batch} backHref={backHref} onReset={() => void handleFile(null)} />}
        </CardBody>
      </Card>
    </>
  );
}

function BatchResult({
  batch,
  backHref,
  onReset,
}: {
  batch: IssuanceBatch;
  backHref: string;
  onReset: () => void;
}) {
  const failed = batch.status === "FAILED";

  return (
    <div className="mt-5">
      <div
        className="rounded-[var(--radius-card)] border p-5"
        style={{
          backgroundColor: failed ? "var(--color-danger-surface)" : "var(--color-verified-surface)",
          borderColor: failed ? "var(--color-danger)" : "var(--color-verified-border)",
        }}
        role="status"
      >
        <p className="text-sm font-semibold text-text">
          {batch.accepted_rows} of {batch.total_rows} row
          {batch.total_rows === 1 ? "" : "s"} accepted
        </p>
        <p className="mt-1 text-sm text-text-muted">
          {batch.anchor_tx_hash ? (
            <>
              Anchored in one transaction —{" "}
              <TxLink hash={batch.anchor_tx_hash} className="break-all text-xs" />
            </>
          ) : (
            "Queued for the ledger. They anchor automatically once the node accepts them."
          )}
        </p>

        <div className="mt-3 flex flex-wrap gap-2">
          <Link href={backHref}>
            <Button variant="secondary">Back to dashboard</Button>
          </Link>
          <Button variant="ghost" onClick={onReset}>
            Upload another
          </Button>
        </div>
      </div>

      {batch.errors.length > 0 && (
        <div className="mt-4">
          <h2 className="text-sm font-semibold tracking-tight">
            Rows that were not issued ({batch.errors.length})
          </h2>
          <p className="mt-1 text-xs text-text-subtle">
            Fix these in your spreadsheet and upload just those rows again.
          </p>
          <div className="mt-2 max-h-72 overflow-auto rounded-[var(--radius-card)] border border-border">
            <table className="w-full text-left text-sm">
              <thead className="bg-surface-muted text-xs text-text-subtle">
                <tr>
                  <th className="px-3 py-2 font-medium">Row</th>
                  <th className="px-3 py-2 font-medium">Email</th>
                  <th className="px-3 py-2 font-medium">Why</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {batch.errors.map((rowError) => (
                  <tr key={rowError.row_number}>
                    <td className="px-3 py-2 tabular-nums">{rowError.row_number}</td>
                    <td className="px-3 py-2 font-mono text-xs">
                      {rowError.raw_row.email || "—"}
                    </td>
                    <td className="px-3 py-2 text-xs">{rowError.error}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
