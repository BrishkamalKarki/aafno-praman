"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { ChangePassword } from "@/components/account/change-password";
import { Card, CardBody } from "@/components/ui/card";
import { ErrorState, FormError, inputClass, labelClass } from "@/components/ui/form";
import { errorMessage } from "@/lib/api/errors";
import { useSeekerProfile, useUpdateSeekerProfile } from "@/lib/api/hooks";
import { formatDate } from "@/lib/api/types";
import { useAuth } from "@/lib/auth/auth-context";
import { useToast } from "@/lib/toast";

/**
 * The holder's account.
 *
 * Almost everything here is read-only, and that is the design rather than an
 * unfinished form. Legal name is part of the hashed payload of every credential
 * issued to this account, so letting the subject edit it would invalidate their
 * own degrees. The citizenship number is set only by an approved issuer
 * attesting to a number it already holds on file — self-assertion is exactly
 * what would make the CITIZENSHIP identity level meaningless.
 *
 * What a citizen genuinely controls is how they describe themselves and whether
 * employers may find them. Those two fields are editable; the rest says who to
 * ask.
 */
export default function ProfilePage() {
  const { user } = useAuth();
  const profile = useSeekerProfile();
  const update = useUpdateSeekerProfile();
  const { notify } = useToast();

  /**
   * The form is a draft laid over the server's value, not a copy of it.
   *
   * Seeding state from a query in an effect means an extra render and, worse, a
   * refetch landing mid-edit can overwrite what someone is typing. Reading
   * `draft ?? server` during render has neither problem: untouched fields
   * always show the truth, and touched ones always show the edit.
   */
  const [draft, setDraft] = useState<{ headline: string; discoverable: boolean } | null>(null);
  const [error, setError] = useState<string | null>(null);

  const headline = draft?.headline ?? profile.data?.headline ?? "";
  const discoverable = draft?.discoverable ?? profile.data?.is_discoverable ?? false;

  function edit(patch: Partial<{ headline: string; discoverable: boolean }>) {
    setDraft({ headline, discoverable, ...patch });
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      await update.mutateAsync({ headline: headline.trim(), is_discoverable: discoverable });
      // Drop the draft so the form falls back to what the server now holds.
      setDraft(null);
      notify("Profile updated.", "success");
    } catch (caught) {
      setError(errorMessage(caught, "Could not save your profile."));
    }
  }

  if (profile.isError) {
    return (
      <div className="mx-auto w-full max-w-2xl">
        <ErrorState
          message={errorMessage(profile.error)}
          onRetry={() => void profile.refetch()}
        />
      </div>
    );
  }

  const data = profile.data;

  return (
    <div className="mx-auto w-full max-w-2xl">
      <h1 className="text-lg font-semibold tracking-tight">Account</h1>
      <p className="mt-1.5 max-w-lg text-sm text-text-muted">
        This is what institutions attest against when they issue you a credential. Contact the
        issuing organisation to correct anything that is fixed here.
      </p>

      <Card className="mt-6">
        <CardBody className="grid gap-5 pt-5 sm:grid-cols-2">
          <ReadOnly label="Full name" value={data?.legal_name || user?.full_name} />
          <ReadOnly label="Email" value={data?.email || user?.email} />
          <ReadOnly label="Phone" value={data?.phone || user?.phone} />
          <ReadOnly label="Date of birth" value={formatDate(data?.date_of_birth)} />
          <ReadOnly
            label="Citizenship number"
            value={data?.national_id_masked || "Not attested"}
            hint={
              data?.identity_level === "CITIZENSHIP"
                ? `Verified by ${data.citizenship_verified_by_name || "an approved issuer"}`
                : "No institution has attested one, so verifiers cannot confirm ownership by ID."
            }
          />
          <ReadOnly
            label="Identity level"
            value={
              data?.identity_level === "CITIZENSHIP"
                ? "Citizenship verified by an issuer"
                : "Email confirmed"
            }
            hint="Employers are told which of these applies, so nothing is implied that was never established."
          />
        </CardBody>
      </Card>

      <Card className="mt-6">
        <CardBody className="pt-5">
          <h2 className="text-sm font-semibold tracking-tight">What you control</h2>

          <form onSubmit={handleSubmit} className="mt-4 space-y-5">
            <FormError message={error} />

            <div>
              <label htmlFor="headline" className={labelClass}>
                Headline
              </label>
              <input
                id="headline"
                maxLength={160}
                value={headline}
                onChange={(event) => edit({ headline: event.target.value })}
                placeholder="e.g. BSc CSIT graduate — backend developer"
                className={inputClass}
              />
              <p className="mt-1 text-xs text-text-subtle">
                Shown on your shared passport, above your credentials.
              </p>
            </div>

            <label className="flex items-start gap-2 text-sm">
              <input
                type="checkbox"
                checked={discoverable}
                onChange={(event) => edit({ discoverable: event.target.checked })}
                className="mt-0.5 size-4"
              />
              <span>
                Let employers find me in candidate search
                <span className="block text-xs text-text-subtle">
                  Off by default. Employers see your verified qualifications and headline —
                  never your email, phone, or ID number.
                </span>
              </span>
            </label>

            <Button type="submit" loading={update.isPending} disabled={profile.isPending}>
              Save changes
            </Button>
          </form>
        </CardBody>
      </Card>

      <ChangePassword />
    </div>
  );
}

function ReadOnly({
  label,
  value,
  hint,
}: {
  label: string;
  value: string | null | undefined;
  hint?: string;
}) {
  return (
    <div>
      <p className="text-xs font-medium text-text-subtle uppercase">{label}</p>
      <p className="mt-1 break-words text-sm text-text">{value || "—"}</p>
      {hint && <p className="mt-1 text-xs text-text-subtle">{hint}</p>}
    </div>
  );
}
