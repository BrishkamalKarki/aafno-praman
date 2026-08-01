"use client";

import { useState } from "react";

import { ChangePassword } from "@/components/account/change-password";
import { Button } from "@/components/ui/button";
import { Card, CardBody } from "@/components/ui/card";
import { EmptyState, ListCard, ListRow } from "@/components/ui/dashboard";
import { ErrorState, FileField, FormError, inputClass, labelClass, LoadingRows } from "@/components/ui/form";
import { errorMessage } from "@/lib/api/errors";
import {
  useMyOrganization,
  useOrganizationDocuments,
  useOrganizationMembers,
  useUploadOrganizationDocument,
} from "@/lib/api/hooks";
import { formatDate, shortHash, timeAgo } from "@/lib/api/types";
import { useToast } from "@/lib/toast";

/**
 * The organisation's own record: who it is on chain, who its staff are, and
 * what accreditation it has filed.
 *
 * All three read endpoints existed with nothing calling them, which left an
 * institution unable to see its own signing address, its own team, or whether
 * the accreditation letter it was asked for had ever arrived. The document
 * upload in particular is the registrar's evidence trail — the thing the whole
 * approval decision is supposed to rest on — and it had no way in at all.
 */

const DOC_TYPES = [
  { value: "ACCREDITATION", label: "Accreditation certificate" },
  { value: "REGISTRATION", label: "Registration / PAN certificate" },
  { value: "AUTHORISATION", label: "Letter of authorisation" },
  { value: "OTHER", label: "Something else" },
] as const;

export function OrganizationPanel() {
  const organization = useMyOrganization();
  const members = useOrganizationMembers();

  return (
    <div className="mx-auto w-full max-w-3xl space-y-6">
      <div>
        <h1 className="text-lg font-semibold tracking-tight">Organisation</h1>
        <p className="mt-1.5 text-sm text-text-muted">
          What this organisation is on the platform and on the ledger.
        </p>
      </div>

      {organization.isError ? (
        <ErrorState
          message={errorMessage(organization.error)}
          onRetry={() => void organization.refetch()}
        />
      ) : (
        <Card>
          <CardBody className="grid gap-4 pt-5 sm:grid-cols-2">
            <Field label="Legal name" value={organization.data?.legal_name} />
            <Field
              label="Kind"
              value={
                organization.data?.kind === "INSTITUTION"
                  ? "Educational institution"
                  : organization.data?.kind === "EMPLOYER"
                    ? "Employer"
                    : undefined
              }
            />
            <Field label="Registration number" value={organization.data?.registration_number} />
            <Field label="Status" value={organization.data?.status} />
            <Field label="Contact" value={organization.data?.contact_email} />
            <Field label="Plan" value={organization.data?.plan} />

            {organization.data?.status_reason && (
              <div className="sm:col-span-2">
                <p className="text-xs font-medium text-text-subtle uppercase">
                  Reason on file from the registrar
                </p>
                <p className="mt-1 text-sm text-text">{organization.data.status_reason}</p>
              </div>
            )}

            <div className="sm:col-span-2 border-t border-border pt-4">
              <p className="text-xs font-medium text-text-subtle uppercase">On-chain identity</p>
              {/* The address is evidence, not a setting. It is what a verifier
                  sees against every credential this organisation issues, and
                  the platform holds the key — nobody here installs a wallet. */}
              <p className="mt-1 font-mono text-xs break-all text-text">
                {organization.data?.chain_address || "Not registered on chain yet"}
              </p>
              {organization.data?.approval_tx_hash && (
                <p className="mt-1 text-xs text-text-subtle">
                  Approved {formatDate(organization.data.approved_at)} in{" "}
                  <span className="font-mono">
                    {shortHash(organization.data.approval_tx_hash, 14)}
                  </span>
                </p>
              )}
              <p className="mt-2 text-xs text-text-subtle">
                Credentials are signed with a key the platform generates and holds for you. There
                is no wallet to install and no gas to pay.
              </p>
            </div>
          </CardBody>
        </Card>
      )}

      <section aria-labelledby="team">
        <h2 id="team" className="mb-3 text-sm font-semibold tracking-tight">
          Team
        </h2>
        {members.isPending ? (
          <LoadingRows rows={2} />
        ) : (members.data?.length ?? 0) === 0 ? (
          <EmptyState
            icon="user"
            title="No members listed"
            description="Staff accounts are created by the platform registrar."
          />
        ) : (
          <ListCard>
            {members.data?.map((member) => (
              <ListRow
                key={member.id}
                title={member.full_name || member.email}
                meta={`${member.email} · joined ${timeAgo(member.created_at)}`}
                trailing={
                  <span className="shrink-0 rounded-full border border-border bg-surface-muted px-2.5 py-1 text-xs font-medium text-text-muted">
                    {member.role.charAt(0) + member.role.slice(1).toLowerCase()}
                  </span>
                }
              />
            ))}
          </ListCard>
        )}
        <p className="mt-2 text-xs text-text-subtle">
          Adding a colleague is a registrar action in this build — there is no invite flow yet.
        </p>
      </section>

      <AccreditationDocuments />

      <ChangePassword />
    </div>
  );
}

function AccreditationDocuments() {
  const documents = useOrganizationDocuments();
  const upload = useUploadOrganizationDocument();
  const { notify } = useToast();

  const [file, setFile] = useState<File | null>(null);
  const [docType, setDocType] = useState<string>(DOC_TYPES[0].value);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!file) return;

    setError(null);
    try {
      await upload.mutateAsync({ file, doc_type: docType });
      setFile(null);
      notify("Document uploaded.", "success");
    } catch (caught) {
      setError(errorMessage(caught, "Could not upload that document."));
    }
  }

  return (
    <section aria-labelledby="documents">
      <h2 id="documents" className="mb-3 text-sm font-semibold tracking-tight">
        Accreditation documents
      </h2>

      {documents.isPending ? (
        <LoadingRows rows={2} />
      ) : (documents.data?.length ?? 0) === 0 ? (
        <EmptyState
          icon="file-text"
          title="Nothing filed yet"
          description="Upload the accreditation or registration certificate the registrar checked when approving you."
        />
      ) : (
        <ListCard>
          {documents.data?.map((document) => (
            <ListRow
              key={document.id}
              title={
                DOC_TYPES.find((entry) => entry.value === document.doc_type)?.label ??
                document.doc_type
              }
              // The stored SHA-256 is what makes the filing evidence rather
              // than a copy: the registrar can tell whether the file they
              // reviewed is still the file on record.
              subtitle={`sha256 ${document.sha256.slice(0, 24)}…`}
              meta={`Uploaded ${timeAgo(document.created_at)}`}
            />
          ))}
        </ListCard>
      )}

      <Card className="mt-4">
        <CardBody className="pt-5">
          <form onSubmit={submit} className="space-y-4">
            <FormError message={error} />

            <div>
              <label htmlFor="doc_type" className={labelClass}>
                Document type
              </label>
              <select
                id="doc_type"
                value={docType}
                onChange={(event) => setDocType(event.target.value)}
                className={inputClass}
              >
                {DOC_TYPES.map((entry) => (
                  <option key={entry.value} value={entry.value}>
                    {entry.label}
                  </option>
                ))}
              </select>
            </div>

            <FileField
              id="org-document"
              label="File"
              accept=".pdf,.png,.jpg,.jpeg"
              file={file}
              onSelect={setFile}
              hint="PDF, PNG or JPEG. Stored privately with its hash, and visible only to your organisation and the registrar."
            />

            <Button type="submit" loading={upload.isPending} disabled={!file}>
              Upload document
            </Button>
          </form>
        </CardBody>
      </Card>
    </section>
  );
}

function Field({ label, value }: { label: string; value: string | null | undefined }) {
  return (
    <div>
      <p className="text-xs font-medium text-text-subtle uppercase">{label}</p>
      <p className="mt-1 break-words text-sm text-text">{value || "—"}</p>
    </div>
  );
}
