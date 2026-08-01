"use client";

import { useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";

import { homeFor, useAuth, type OrgKind, type Role } from "@/lib/auth/auth-context";

/**
 * Guards a console.
 *
 * This is convenience, not a security boundary — every route behind it is
 * enforced by DRF permission classes that re-read the user's role and their
 * organisation's status from the database on each request. What this prevents is
 * a citizen who types `/admin` seeing a shell full of failed requests instead of
 * being taken somewhere useful.
 *
 * A user in the wrong place is redirected to their own console rather than shown
 * a 403 page: they are not doing anything wrong, they followed a stale link.
 */
export function ProtectedRoute({
  allow,
  requireOrgKind,
  children,
}: {
  allow: readonly Role[];
  /** For ORG_MEMBER consoles, narrow further — an employer is not an issuer. */
  requireOrgKind?: OrgKind;
  children: React.ReactNode;
}) {
  const { user, status, primaryOrg } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  const wrongRole = user !== null && !allow.includes(user.role);
  const wrongOrgKind =
    requireOrgKind !== undefined &&
    user?.role === "ORG_MEMBER" &&
    primaryOrg !== null &&
    primaryOrg.kind !== requireOrgKind;

  useEffect(() => {
    if (status === "loading") return;

    if (status === "unauthenticated") {
      // Carry the destination so signing in resumes where they were headed,
      // rather than dumping everyone on their dashboard root.
      router.replace(`/login?next=${encodeURIComponent(pathname)}`);
      return;
    }
    if (user && (wrongRole || wrongOrgKind)) {
      router.replace(homeFor(user.role, primaryOrg?.kind));
    }
  }, [status, user, wrongRole, wrongOrgKind, primaryOrg, router, pathname]);

  if (status !== "authenticated" || wrongRole || wrongOrgKind) {
    return <RouteSpinner />;
  }
  return <>{children}</>;
}

/**
 * Shown while the session is being restored or a redirect is in flight.
 *
 * Deliberately not a skeleton of the page behind it: rendering a convincing
 * dashboard outline to someone who is about to be bounced to the login screen
 * reads as the app losing their data.
 */
export function RouteSpinner() {
  return (
    <div className="flex min-h-dvh w-full items-center justify-center">
      <span
        role="status"
        aria-label="Loading"
        className="size-8 animate-spin rounded-full border-2 border-border-strong border-t-brand"
      />
    </div>
  );
}
