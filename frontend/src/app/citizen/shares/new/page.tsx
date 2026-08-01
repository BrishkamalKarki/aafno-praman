"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardBody } from "@/components/ui/card";
import { EmptyState, ListCard, ListRow } from "@/components/ui/dashboard";
import { FormError, inputClass, labelClass, LoadingRows } from "@/components/ui/form";
import { Icon } from "@/components/ui/icon";
import { errorMessage } from "@/lib/api/errors";
import {
  useCreateShareLink,
  useMyShareLinkQr,
  usePassport,
  useRevokeShareLink,
  useShareLinks,
} from "@/lib/api/hooks";
import { formatDate, recordTitle, timeAgo } from "@/lib/api/types";
import { useToast } from "@/lib/toast";

/**
 * Create a scoped, revocable link an employer can open without an account.
 *
 * Three controls, each of which exists because of a specific failure of the
 * alternative:
 *
 * * **Which credentials.** Sharing everything to prove one degree hands a
 *   recruiter a complete employment history they never asked for.
 * * **Mask identifiers.** Registration and citizenship numbers are shown as
 *   their last three characters — enough to confirm a number the verifier was
 *   already given, not enough to harvest one.
 * * **Expiry and passphrase.** A link that lives forever is a credential
 *   published to anyone who ever sees the URL.
 */
export default function NewSharePage() {
  const passport = usePassport();
  const shareLinks = useShareLinks();
  const create = useCreateShareLink();
  const revoke = useRevokeShareLink();
  const { notify } = useToast();

  const [label, setLabel] = useState("");
  const [includeAll, setIncludeAll] = useState(true);
  const [selected, setSelected] = useState<string[]>([]);
  const [mask, setMask] = useState(true);
  const [expiresAt, setExpiresAt] = useState("");
  const [passphrase, setPassphrase] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [created, setCreated] = useState<string | null>(null);

  // Computed once, lazily: reading the clock during render makes the component
  // impure, and the earliest sensible expiry does not change while the form is
  // open anyway.
  const [earliestExpiry] = useState(() =>
    new Date(Date.now() + 86_400_000).toISOString().slice(0, 10),
  );

  // Only issued records can be shared: an offer nobody has accepted is not yet
  // a credential, and a declined one never will be.
  const shareable = (passport.data?.records ?? []).filter(
    (record) => record.status === "ISSUED",
  );

  function toggle(id: string) {
    setSelected((current) =>
      current.includes(id) ? current.filter((entry) => entry !== id) : [...current, id],
    );
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);

    if (!includeAll && selected.length === 0) {
      setError("Select at least one credential, or share everything.");
      return;
    }

    try {
      const link = await create.mutateAsync({
        label: label.trim() || "Shared credentials",
        include_all: includeAll,
        mask_identifiers: mask,
        ...(includeAll ? {} : { record_ids: selected }),
        // A date input gives a day; the API wants an instant. End of that day is
        // what someone means by "expires on the 12th".
        ...(expiresAt ? { expires_at: new Date(`${expiresAt}T23:59:59`).toISOString() } : {}),
        ...(passphrase.trim() ? { passphrase: passphrase.trim() } : {}),
      });

      setCreated(link.url);
      setLabel("");
      setSelected([]);
      setPassphrase("");
      setExpiresAt("");
      notify("Share link created.", "success");
    } catch (caught) {
      setError(errorMessage(caught, "Could not create the link."));
    }
  }

  async function handleRevoke(id: string) {
    try {
      await revoke.mutateAsync(id);
      notify("Link revoked. Anyone holding it now sees nothing.", "info");
    } catch (caught) {
      notify(errorMessage(caught, "Could not revoke the link."), "danger");
    }
  }

  return (
    <div className="mx-auto w-full max-w-3xl">
      <h1 className="text-lg font-semibold tracking-tight">Share a credential</h1>
      <p className="mt-1.5 text-sm text-text-muted">
        Creates a link an employer can open without an account. You can revoke it at any time.
      </p>

      {created && <CreatedLink url={created} onDismiss={() => setCreated(null)} />}

      <Card className="mt-6">
        <CardBody className="pt-5">
          <form onSubmit={handleSubmit} className="space-y-5">
            <FormError message={error} />

            <div>
              <label htmlFor="label" className={labelClass}>
                What is this for?{" "}
                <span className="font-normal text-text-subtle">(only you see this)</span>
              </label>
              <input
                id="label"
                value={label}
                onChange={(event) => setLabel(event.target.value)}
                placeholder="e.g. Leapfrog application"
                className={inputClass}
              />
            </div>

            <fieldset className="space-y-3">
              <legend className={labelClass}>Which credentials</legend>

              <label className="flex items-center gap-2 text-sm">
                <input
                  type="radio"
                  name="scope"
                  checked={includeAll}
                  onChange={() => setIncludeAll(true)}
                  className="size-4"
                />
                Everything I hold
              </label>
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="radio"
                  name="scope"
                  checked={!includeAll}
                  onChange={() => setIncludeAll(false)}
                  className="size-4"
                />
                Only the ones I pick
              </label>

              {!includeAll && (
                <div className="mt-2 space-y-2 rounded-[var(--radius-card)] border border-border p-3">
                  {passport.isPending ? (
                    <LoadingRows rows={2} />
                  ) : shareable.length === 0 ? (
                    <p className="text-sm text-text-muted">
                      You have no confirmed credentials to share yet.
                    </p>
                  ) : (
                    shareable.map((record) => (
                      <label key={record.id} className="flex items-start gap-2 text-sm">
                        <input
                          type="checkbox"
                          checked={selected.includes(record.id)}
                          onChange={() => toggle(record.id)}
                          className="mt-0.5 size-4"
                        />
                        <span>
                          <span className="font-medium">{recordTitle(record)}</span>
                          <span className="block text-xs text-text-subtle">
                            {record.issuer_name}
                          </span>
                        </span>
                      </label>
                    ))
                  )}
                </div>
              )}
            </fieldset>

            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <label htmlFor="expires" className={labelClass}>
                  Expires on{" "}
                  <span className="font-normal text-text-subtle">(optional)</span>
                </label>
                <input
                  id="expires"
                  type="date"
                  value={expiresAt}
                  min={earliestExpiry}
                  onChange={(event) => setExpiresAt(event.target.value)}
                  className={inputClass}
                />
              </div>
              <div>
                <label htmlFor="passphrase" className={labelClass}>
                  Passphrase <span className="font-normal text-text-subtle">(optional)</span>
                </label>
                <input
                  id="passphrase"
                  value={passphrase}
                  minLength={4}
                  onChange={(event) => setPassphrase(event.target.value)}
                  className={inputClass}
                  autoComplete="off"
                />
              </div>
            </div>

            <label className="flex items-start gap-2 text-sm">
              <input
                type="checkbox"
                checked={mask}
                onChange={(event) => setMask(event.target.checked)}
                className="mt-0.5 size-4"
              />
              <span>
                Hide most of my registration and ID numbers
                <span className="block text-xs text-text-subtle">
                  The last three characters are still shown, so a verifier can confirm a
                  number they already have.
                </span>
              </span>
            </label>

            <Button type="submit" size="lg" loading={create.isPending}>
              Create share link
            </Button>
          </form>
        </CardBody>
      </Card>

      <section aria-labelledby="existing" className="mt-8">
        <h2 id="existing" className="mb-3 text-sm font-semibold tracking-tight">
          Your share links
        </h2>

        {shareLinks.isPending ? (
          <LoadingRows rows={2} />
        ) : (shareLinks.data?.length ?? 0) === 0 ? (
          <EmptyState
            icon="link"
            title="No links yet"
            description="Create one above to send proof of a credential to an employer."
          />
        ) : (
          <ListCard>
            {shareLinks.data?.map((link) => (
              <ListRow
                key={link.id}
                title={link.label || "Shared credentials"}
                subtitle={link.url}
                meta={[
                  link.is_active ? "Active" : "Revoked or expired",
                  `${link.record_count} credential${link.record_count === 1 ? "" : "s"}`,
                  `${link.view_count} view${link.view_count === 1 ? "" : "s"}`,
                  link.expires_at ? `expires ${formatDate(link.expires_at)}` : "no expiry",
                  link.requires_passphrase ? "passphrase set" : null,
                  `created ${timeAgo(link.created_at)}`,
                ]
                  .filter(Boolean)
                  .join(" · ")}
                trailing={
                  link.is_active ? (
                    <div className="flex shrink-0 items-center gap-1">
                      <CopyButton value={link.url} />
                      <QrButton id={link.id} />
                      <button
                        type="button"
                        onClick={() => void handleRevoke(link.id)}
                        disabled={revoke.isPending}
                        className="rounded-[var(--radius-control)] p-2 text-text-subtle hover:bg-surface-muted"
                        aria-label={`Revoke ${link.label || "this link"}`}
                      >
                        <Icon name="trash" size={16} />
                      </button>
                    </div>
                  ) : null
                }
              />
            ))}
          </ListCard>
        )}
      </section>
    </div>
  );
}

function CreatedLink({ url, onDismiss }: { url: string; onDismiss: () => void }) {
  return (
    <div
      role="status"
      className="mt-6 rounded-[var(--radius-card)] border p-5"
      style={{
        backgroundColor: "var(--color-verified-surface)",
        borderColor: "var(--color-verified-border)",
      }}
    >
      <p className="text-sm font-semibold text-text">Link ready to send</p>
      <p className="mt-1 break-all font-mono text-xs text-text-muted">{url}</p>
      <div className="mt-3 flex flex-wrap gap-2">
        <CopyButton value={url} labelled />
        <Button variant="ghost" onClick={onDismiss}>
          Dismiss
        </Button>
      </div>
    </div>
  );
}

function CopyButton({ value, labelled = false }: { value: string; labelled?: boolean }) {
  const { notify } = useToast();

  async function copy() {
    try {
      await navigator.clipboard.writeText(value);
      notify("Link copied.", "success");
    } catch {
      // Clipboard access is blocked over plain HTTP on some browsers, which is
      // exactly the setup a local demo runs on. Say so rather than failing mute.
      notify("Could not copy automatically — select the link and copy it.", "danger");
    }
  }

  if (labelled) {
    return (
      <Button variant="secondary" onClick={() => void copy()}>
        <Icon name="link" size={16} />
        Copy link
      </Button>
    );
  }

  return (
    <button
      type="button"
      onClick={() => void copy()}
      className="rounded-[var(--radius-control)] p-2 text-text-subtle hover:bg-surface-muted"
      aria-label="Copy link"
    >
      <Icon name="link" size={16} />
    </button>
  );
}

/**
 * Opens the QR PNG the backend renders.
 *
 * Fetched rather than linked because the endpoint is authenticated — an `<img
 * src>` carries no Authorization header, so a plain link would 401.
 */
function QrButton({ id }: { id: string }) {
  const { fetchQr, isPending } = useMyShareLinkQr();
  const { notify } = useToast();

  async function open() {
    try {
      const blobUrl = await fetchQr(id);
      window.open(blobUrl, "_blank", "noopener");
    } catch {
      notify("Could not load the QR code.", "danger");
    }
  }

  return (
    <button
      type="button"
      onClick={() => void open()}
      disabled={isPending}
      className="rounded-[var(--radius-control)] p-2 text-text-subtle hover:bg-surface-muted"
      aria-label="Show QR code"
    >
      <Icon name="grid" size={16} />
    </button>
  );
}
