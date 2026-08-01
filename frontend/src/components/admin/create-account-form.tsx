"use client";

import { useState } from "react";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import { Card, CardBody } from "@/components/ui/card";
import { FormError, inputClass, labelClass, textareaClass } from "@/components/ui/form";
import { Icon } from "@/components/ui/icon";
import { errorMessage } from "@/lib/api/errors";
import { useProvisionAccount, type ProvisionResult } from "@/lib/api/hooks";
import { useToast } from "@/lib/toast";

export interface AccountField {
  id: string;
  label: string;
  type?: "text" | "email" | "tel" | "date" | "url" | "textarea" | "select";
  required?: boolean;
  autoComplete?: string;
  placeholder?: string;
  options?: readonly { value: string; label: string }[];
  help?: string;
  /** Full width in the two-column layout. */
  wide?: boolean;
}

/**
 * Provisions one account and hands back its login.
 *
 * There is no self-registration for organisations on this platform — an
 * institution that could register itself could mint degrees, which is the exact
 * vulnerability the registrar exists to close. So a registrar fills this in on
 * the organisation's or citizen's behalf, and the generated password is the only
 * way into that account until its owner changes it.
 *
 * The password is shown once and is not retrievable. That is a real limitation
 * rather than a design flourish: there is no password-reset email in this MVP,
 * so the screen says to write it down instead of implying a recovery path that
 * does not exist.
 *
 * For an organisation, the same request also registers it on chain. That call is
 * chain-first and atomic — if the ledger is unreachable, nothing is created and
 * the registrar simply submits the form again.
 */
export function CreateAccountForm({
  target,
  fields,
  fixedValues,
  backHref,
  successNote,
}: {
  target: "user" | "organization";
  fields: readonly AccountField[];
  /** Values the form does not ask for, e.g. an organisation's `kind`. */
  fixedValues?: Record<string, string>;
  backHref: string;
  successNote: string;
}) {
  const provision = useProvisionAccount(target);
  const { notify } = useToast();

  const [values, setValues] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [created, setCreated] = useState<ProvisionResult | null>(null);

  function update(id: string, value: string) {
    setValues((current) => ({ ...current, [id]: value }));
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);

    // Blank optional fields are dropped rather than sent as "": DRF rejects an
    // empty string for a date or a URL, and "this field may not be blank" for
    // something the form called optional is a confusing way to fail.
    const payload: Record<string, string> = { ...fixedValues };
    for (const [key, value] of Object.entries(values)) {
      if (value.trim()) payload[key] = value.trim();
    }

    try {
      const result = await provision.mutateAsync(
        payload as unknown as Parameters<typeof provision.mutateAsync>[0],
      );
      setCreated(result);
      notify("Account created.", "success");
    } catch (caught) {
      setError(errorMessage(caught, "Could not create this account."));
    }
  }

  if (created) {
    return (
      <Card raised className="mt-6">
        <CardBody className="flex flex-col items-center gap-3 pt-8 pb-8 text-center">
          <span className="flex size-11 items-center justify-center rounded-full bg-verified-surface text-verified">
            <Icon name="shield-check" size={20} />
          </span>
          <p className="text-base font-semibold tracking-tight">Account created</p>
          <p className="max-w-sm text-sm text-text-muted">{successNote}</p>

          <div className="mt-2 w-full max-w-xs rounded-[var(--radius-card)] border border-border bg-surface-muted p-4 text-left text-sm">
            <p className="text-xs font-medium text-text-subtle uppercase">Login email</p>
            <p className="mt-0.5 font-mono break-all">{created.user.email}</p>
            <p className="mt-3 text-xs font-medium text-text-subtle uppercase">
              Temporary password
            </p>
            <p className="mt-0.5 font-mono">{created.temp_password}</p>

            {created.organization?.chain_address && (
              <>
                <p className="mt-3 text-xs font-medium text-text-subtle uppercase">
                  On-chain signing address
                </p>
                <p className="mt-0.5 font-mono text-xs break-all">
                  {created.organization.chain_address}
                </p>
                <p className="mt-2 text-xs text-text-subtle">
                  Registered on the ledger — this organisation can issue immediately.
                </p>
              </>
            )}
          </div>

          {/* Said plainly because it is true: there is no reset email in this
              build, so a password lost here means the account is unreachable. */}
          <p className="max-w-xs text-xs text-text-subtle">
            Write this down now and share it with them directly. It cannot be shown again.
          </p>

          <div className="mt-2 flex gap-2">
            <Link href={backHref}>
              <Button variant="secondary">Back to dashboard</Button>
            </Link>
            <Button
              variant="ghost"
              onClick={() => {
                setValues({});
                setCreated(null);
              }}
            >
              Create another
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
            {fields.map((field) => (
              <div key={field.id} className={field.wide ? "sm:col-span-2" : undefined}>
                <label htmlFor={field.id} className={labelClass}>
                  {field.label}
                  {!field.required && (
                    <span className="font-normal text-text-subtle"> (optional)</span>
                  )}
                </label>

                {field.type === "textarea" ? (
                  <textarea
                    id={field.id}
                    required={field.required}
                    placeholder={field.placeholder}
                    value={values[field.id] ?? ""}
                    onChange={(event) => update(field.id, event.target.value)}
                    rows={2}
                    className={textareaClass}
                  />
                ) : field.type === "select" ? (
                  <select
                    id={field.id}
                    required={field.required}
                    value={values[field.id] ?? ""}
                    onChange={(event) => update(field.id, event.target.value)}
                    className={inputClass}
                  >
                    <option value="" disabled>
                      Select…
                    </option>
                    {field.options?.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                ) : (
                  <input
                    id={field.id}
                    type={field.type ?? "text"}
                    required={field.required}
                    placeholder={field.placeholder}
                    autoComplete={field.autoComplete}
                    value={values[field.id] ?? ""}
                    onChange={(event) => update(field.id, event.target.value)}
                    className={inputClass}
                  />
                )}

                {field.help && <p className="mt-1 text-xs text-text-subtle">{field.help}</p>}
              </div>
            ))}
          </div>

          <Button type="submit" size="lg" loading={provision.isPending}>
            Create account
          </Button>
        </form>
      </CardBody>
    </Card>
  );
}
