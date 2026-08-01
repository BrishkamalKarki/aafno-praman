"use client";

import { useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { RouteSpinner } from "@/components/auth/protected-route";
import { Logo } from "@/components/brand/logo";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardTitle } from "@/components/ui/card";
import { Icon, type IconName } from "@/components/ui/icon";
import { homeFor, useAuth } from "@/lib/auth/auth-context";

/**
 * Role select — the only thing on this screen.
 *
 * Not a landing page. Everyone who reaches this app already knows what Aafno Praman
 * is; what they need is to get to their own console in one tap. No marketing
 * copy, no explanation of how verification works — that lives inside each
 * console where it is actually relevant.
 *
 * The tiles are signposts, not a choice of identity: picking one leads to sign
 * in, and where you end up is decided by what your account actually is. Someone
 * already signed in never sees this screen at all — they are sent to their own
 * console, because being asked "who are you?" by a site that already knows is
 * the moment a person stops trusting it.
 */

const ROLES: Array<{ href: string; title: string; icon: IconName }> = [
  { href: "/admin", title: "Admin", icon: "grid" },
  { href: "/citizen", title: "Users", icon: "user" },
  { href: "/employer", title: "Company", icon: "building" },
  { href: "/issuer", title: "Edu Institution", icon: "shield-check" },
];

export default function RoleSelectPage() {
  const { status, user, primaryOrg } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (status === "authenticated" && user) {
      router.replace(homeFor(user.role, primaryOrg?.kind));
    }
  }, [status, user, primaryOrg, router]);

  if (status === "loading" || status === "authenticated") {
    return <RouteSpinner />;
  }

  return (
    <main
      id="main"
      className="mx-auto flex min-h-dvh w-full max-w-lg flex-col items-center justify-center px-5 py-16"
    >
      <Logo className="text-sm text-brand" size={22} />
      <h1 className="mt-2 text-center text-2xl font-semibold tracking-tight">Continue as</h1>

      <div className="mt-8 grid w-full grid-cols-2 gap-3">
        {ROLES.map((role) => (
          <Card
            key={role.href}
            raised
            className="relative transition-colors hover:border-brand-border focus-within:border-brand"
          >
            <CardBody className="flex flex-col items-center gap-3 py-7 text-center">
              <span className="flex size-11 items-center justify-center rounded-full bg-brand-subtle text-brand">
                <Icon name={role.icon} size={20} />
              </span>
              <CardTitle className="text-base">
                <Link
                  href={`/login?next=${encodeURIComponent(role.href)}`}
                  className="after:absolute after:inset-0"
                >
                  {role.title}
                </Link>
              </CardTitle>
            </CardBody>
          </Card>
        ))}
      </div>

      <div className="mt-8 flex flex-col items-center gap-3">
        <Link href="/login">
          <Button size="lg">Sign in</Button>
        </Link>
        <p className="text-sm text-text-muted">
          New here?{" "}
          <Link href="/register" className="font-medium text-brand hover:underline">
            Create a citizen account
          </Link>
        </p>
      </div>
    </main>
  );
}
