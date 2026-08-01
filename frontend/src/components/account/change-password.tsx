"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardBody } from "@/components/ui/card";
import { FormError, inputClass, labelClass } from "@/components/ui/form";
import { errorMessage } from "@/lib/api/errors";
import { useChangePassword } from "@/lib/api/hooks";
import { useToast } from "@/lib/toast";

/**
 * Set a new password.
 *
 * Not optional polish. Institutions, employers and citizens are all provisioned
 * by the registrar with a generated password handed over in person or down a
 * phone line — and with no screen to change it, every account on the platform
 * was permanently stuck on a secret that a third party had also seen and
 * written down somewhere. The endpoint existed the whole time; nothing called
 * it.
 *
 * Existing refresh tokens stay valid afterwards. There is no blacklist app
 * installed, so they cannot be revoked, and the copy says so rather than
 * implying that changing the password kicks out whoever else was signed in.
 */
export function ChangePassword() {
  const changePassword = useChangePassword();
  const { notify } = useToast();

  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();

    // Checked here as well as server-side so a typo is caught before a round
    // trip clears both fields.
    if (next !== confirm) {
      setError("The two new passwords do not match.");
      return;
    }

    setError(null);
    try {
      await changePassword.mutateAsync({ current_password: current, new_password: next });
      setCurrent("");
      setNext("");
      setConfirm("");
      notify("Password changed.", "success");
    } catch (caught) {
      setError(errorMessage(caught, "Could not change your password."));
    }
  }

  return (
    <Card className="mt-6">
      <CardBody className="pt-5">
        <h2 className="text-sm font-semibold tracking-tight">Password</h2>
        <p className="mt-1 text-sm text-text-muted">
          If your account was set up for you, change the password you were given.
        </p>

        <form onSubmit={handleSubmit} className="mt-4 space-y-4">
          <FormError message={error} />

          <div>
            <label htmlFor="current_password" className={labelClass}>
              Current password
            </label>
            <input
              id="current_password"
              type="password"
              required
              autoComplete="current-password"
              value={current}
              onChange={(event) => setCurrent(event.target.value)}
              className={inputClass}
            />
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label htmlFor="new_password" className={labelClass}>
                New password
              </label>
              <input
                id="new_password"
                type="password"
                required
                autoComplete="new-password"
                value={next}
                onChange={(event) => setNext(event.target.value)}
                className={inputClass}
              />
            </div>
            <div>
              <label htmlFor="confirm_password" className={labelClass}>
                Confirm new password
              </label>
              <input
                id="confirm_password"
                type="password"
                required
                autoComplete="new-password"
                value={confirm}
                onChange={(event) => setConfirm(event.target.value)}
                className={inputClass}
              />
            </div>
          </div>

          <p className="text-xs text-text-subtle">
            At least 8 characters, and not something obvious. Sessions already signed in
            elsewhere are not signed out — that needs a token blacklist this build does not have.
          </p>

          <Button type="submit" loading={changePassword.isPending}>
            Change password
          </Button>
        </form>
      </CardBody>
    </Card>
  );
}
