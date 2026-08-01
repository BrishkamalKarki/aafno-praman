"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { Logo } from "@/components/brand/logo";
import { Button } from "@/components/ui/button";
import { Card, CardBody } from "@/components/ui/card";
import { FormError, inputClass, labelClass } from "@/components/ui/form";
import { errorMessage } from "@/lib/api/errors";
import { useAuth } from "@/lib/auth/auth-context";
import { useToast } from "@/lib/toast";

/**
 * Citizen self-registration.
 *
 * The only role that may sign itself up. An institution that could self-register
 * could mint degrees, so those accounts come from the registrar instead — see
 * `RegistrationSerializer.validate_role`, which refuses REGISTRAR outright.
 *
 * Registering with an address an issuer has already used links the credentials
 * waiting against it, which is why the copy says what will appear rather than
 * leaving a new graduate to wonder whether their degree was lost.
 */
export default function RegisterPage() {
  const { register } = useAuth();
  const router = useRouter();
  const { notify } = useToast();

  const [values, setValues] = useState({
    full_name: "",
    email: "",
    phone: "",
    password: "",
    password_confirm: "",
  });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function update(field: keyof typeof values, value: string) {
    setValues((current) => ({ ...current, [field]: value }));
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();

    // Checked here as well as server-side so the mismatch is caught before a
    // round trip clears the fields.
    if (values.password !== values.password_confirm) {
      setError("The two passwords do not match.");
      return;
    }

    setSubmitting(true);
    setError(null);
    try {
      await register({
        full_name: values.full_name.trim(),
        email: values.email.trim().toLowerCase(),
        phone: values.phone.trim(),
        password: values.password,
        password_confirm: values.password_confirm,
      });
      notify("Account created. Anything already issued to you is waiting below.", "success");
      router.replace("/citizen");
    } catch (caught) {
      setError(errorMessage(caught, "Could not create the account."));
      setSubmitting(false);
    }
  }

  return (
    <main id="main" className="mx-auto flex min-h-dvh w-full max-w-md flex-col justify-center px-5 py-16">
      <Logo className="text-sm text-brand" size={22} />
      <h1 className="mt-2 text-2xl font-semibold tracking-tight">Create your account</h1>
      <p className="mt-1.5 text-sm text-text-muted">
        Use the email address your college or employer has on file. Credentials
        already issued to it will be waiting for you to confirm.
      </p>

      <Card raised className="mt-6">
        <CardBody className="pt-5">
          <form onSubmit={handleSubmit} className="space-y-4">
            <FormError message={error} />

            <div>
              <label htmlFor="full_name" className={labelClass}>
                Full name
              </label>
              <input
                id="full_name"
                required
                autoComplete="name"
                value={values.full_name}
                onChange={(event) => update("full_name", event.target.value)}
                className={inputClass}
              />
            </div>

            <div>
              <label htmlFor="email" className={labelClass}>
                Email
              </label>
              <input
                id="email"
                type="email"
                required
                autoComplete="email"
                value={values.email}
                onChange={(event) => update("email", event.target.value)}
                className={inputClass}
              />
            </div>

            <div>
              <label htmlFor="phone" className={labelClass}>
                Phone <span className="font-normal text-text-subtle">(optional)</span>
              </label>
              <input
                id="phone"
                type="tel"
                autoComplete="tel"
                value={values.phone}
                onChange={(event) => update("phone", event.target.value)}
                className={inputClass}
              />
            </div>

            <div>
              <label htmlFor="password" className={labelClass}>
                Password
              </label>
              <input
                id="password"
                type="password"
                required
                autoComplete="new-password"
                value={values.password}
                onChange={(event) => update("password", event.target.value)}
                className={inputClass}
              />
              <p className="mt-1 text-xs text-text-subtle">
                At least 8 characters, and not something obvious.
              </p>
            </div>

            <div>
              <label htmlFor="password_confirm" className={labelClass}>
                Confirm password
              </label>
              <input
                id="password_confirm"
                type="password"
                required
                autoComplete="new-password"
                value={values.password_confirm}
                onChange={(event) => update("password_confirm", event.target.value)}
                className={inputClass}
              />
            </div>

            <Button type="submit" size="lg" className="w-full" loading={submitting}>
              Create account
            </Button>
          </form>
        </CardBody>
      </Card>

      <p className="mt-4 text-center text-sm text-text-muted">
        Already have an account?{" "}
        <Link href="/login" className="font-medium text-brand hover:underline">
          Sign in
        </Link>
      </p>
    </main>
  );
}
