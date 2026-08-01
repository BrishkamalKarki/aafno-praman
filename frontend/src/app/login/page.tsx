"use client";

import { Suspense, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";

import { RouteSpinner } from "@/components/auth/protected-route";
import { Logo } from "@/components/brand/logo";
import { Button } from "@/components/ui/button";
import { Card, CardBody } from "@/components/ui/card";
import { FormError, inputClass, labelClass } from "@/components/ui/form";
import { errorMessage } from "@/lib/api/errors";
import { homeFor, useAuth } from "@/lib/auth/auth-context";
import { useToast } from "@/lib/toast";

/**
 * One sign-in screen for all four roles.
 *
 * There is no role picker here on purpose. The role is a property of the
 * account, so asking someone to choose one before authenticating either does
 * nothing (the server ignores it) or lies (it appears to matter). Where they
 * land is decided after the token comes back, from what the account actually is.
 */
function LoginForm() {
  const { login } = useAuth();
  const router = useRouter();
  const params = useSearchParams();
  const { notify } = useToast();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);

    try {
      const user = await login(email.trim().toLowerCase(), password);
      notify(`Signed in as ${user.full_name}.`, "success");

      // Only same-origin paths are honoured. An open redirect on a login form is
      // a phishing primitive: "sign in to Aafno Praman" that lands somewhere else.
      const next = params.get("next");
      const destination =
        next && next.startsWith("/") && !next.startsWith("//")
          ? next
          : homeFor(user.role, user.organizations[0]?.kind);
      router.replace(destination);
    } catch (caught) {
      setError(errorMessage(caught, "Could not sign in. Check your email and password."));
      setSubmitting(false);
    }
  }

  return (
    <main id="main" className="mx-auto flex min-h-dvh w-full max-w-md flex-col justify-center px-5 py-16">
      <Logo className="text-sm text-brand" size={22} />
      <h1 className="mt-2 text-2xl font-semibold tracking-tight">Sign in</h1>
      <p className="mt-1.5 text-sm text-text-muted">
        Citizens, institutions, employers and platform staff all sign in here.
      </p>

      <Card raised className="mt-6">
        <CardBody className="pt-5">
          <form onSubmit={handleSubmit} className="space-y-4">
            <FormError message={error} />

            <div>
              <label htmlFor="email" className={labelClass}>
                Email
              </label>
              <input
                id="email"
                type="email"
                autoComplete="email"
                required
                autoFocus
                value={email}
                onChange={(event) => setEmail(event.target.value)}
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
                autoComplete="current-password"
                required
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                className={inputClass}
              />
            </div>

            <Button type="submit" size="lg" className="w-full" loading={submitting}>
              Sign in
            </Button>
          </form>
        </CardBody>
      </Card>

      <p className="mt-4 text-center text-sm text-text-muted">
        Been issued a credential but have no account?{" "}
        <Link href="/register" className="font-medium text-brand hover:underline">
          Create one
        </Link>
      </p>
      {/* Institutions and employers cannot self-register — the registrar
          provisions them, because self-approval would make the root of trust
          decorative. Saying so here saves a support email. */}
      <p className="mt-2 text-center text-xs text-text-subtle">
        Institution and employer accounts are created by the platform registrar.
      </p>
      <p className="mt-4 text-center text-sm">
        <Link href="/" className="text-text-subtle hover:text-text">
          ← Back
        </Link>
      </p>
    </main>
  );
}

export default function LoginPage() {
  // `useSearchParams` forces a suspense boundary in the app router.
  return (
    <Suspense fallback={<RouteSpinner />}>
      <LoginForm />
    </Suspense>
  );
}
