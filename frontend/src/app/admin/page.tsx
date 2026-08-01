"use client";

import Link from "next/link";

import { LedgerBanner } from "@/components/shell/ledger-banner";
import { Card, CardBody, CardDescription, CardTitle } from "@/components/ui/card";
import { StatGrid, StatTile } from "@/components/ui/dashboard";
import { LoadingStats } from "@/components/ui/form";
import { Icon, type IconName } from "@/components/ui/icon";
import { useRegistrarSummary } from "@/lib/api/hooks";

/**
 * The registrar's console.
 *
 * Two jobs, and deliberately no others: provision accounts, and decide which
 * organisations may issue. The registrar never sees a citizen's credentials,
 * never verifies, and never issues — it is the root of trust, not a superuser.
 */

const CREATE_ACTIONS: Array<{
  href: string;
  title: string;
  description: string;
  icon: IconName;
}> = [
  {
    href: "/admin/create/user",
    title: "Create a user",
    description: "Set up a citizen's dashboard so they can hold and share credentials.",
    icon: "user",
  },
  {
    href: "/admin/create/company",
    title: "Create a company",
    description:
      "Set up an employer dashboard for checking validity and issuing experience letters.",
    icon: "building",
  },
  {
    href: "/admin/create/institution",
    title: "Create an institution",
    description: "Set up a university, college, or school dashboard for issuing credentials.",
    icon: "shield-check",
  },
];

export default function AdminDashboard() {
  const summary = useRegistrarSummary();

  return (
    <div className="mx-auto w-full max-w-3xl space-y-8">
      <LedgerBanner />

      <div>
        <h1 className="text-lg font-semibold tracking-tight">Registrar console</h1>
        <p className="mt-1.5 max-w-xl text-sm text-text-muted">
          Every account on Aafno Praman starts here, and every organisation that can issue was
          approved here.
        </p>
      </div>

      {summary.isPending ? (
        <LoadingStats />
      ) : (
        <StatGrid>
          <StatTile
            label="Awaiting review"
            value={summary.data?.pending ?? 0}
            tone="revoked"
            hint="Cannot issue yet"
          />
          <StatTile
            label="Approved issuers"
            value={summary.data?.approved ?? 0}
            tone="verified"
          />
          <StatTile label="Suspended" value={summary.data?.suspended ?? 0} />
          <StatTile
            label="Credentials issued"
            value={summary.data?.records_issued ?? 0}
            tone="brand"
          />
        </StatGrid>
      )}

      {(summary.data?.pending ?? 0) > 0 && (
        <div
          className="rounded-[var(--radius-card)] border p-5"
          style={{
            backgroundColor: "var(--color-revoked-surface)",
            borderColor: "var(--color-revoked-border)",
          }}
          role="status"
        >
          <p className="text-sm font-semibold text-text">
            {summary.data?.pending} application
            {summary.data?.pending === 1 ? "" : "s"} waiting on you
          </p>
          <p className="mt-1 text-sm text-text-muted">
            Until you decide, they cannot issue anything. Approval registers their signing key
            on the ledger.
          </p>
          <Link
            href="/admin/organizations"
            className="mt-2 inline-block text-sm font-medium text-brand hover:underline"
          >
            Review applications
          </Link>
        </div>
      )}

      <section aria-labelledby="create">
        <h2 id="create" className="mb-3 text-sm font-semibold tracking-tight">
          Create a dashboard
        </h2>
        <div className="grid gap-4 sm:grid-cols-3">
          {CREATE_ACTIONS.map((action) => (
            <Card
              key={action.href}
              raised
              className="relative flex h-full flex-col transition-colors hover:border-brand-border focus-within:border-brand"
            >
              <CardBody className="flex h-full flex-col pt-5">
                <span className="flex size-10 items-center justify-center rounded-full bg-brand-subtle text-brand">
                  <Icon name={action.icon} size={18} />
                </span>
                <CardTitle className="mt-3 text-base">
                  <Link href={action.href} className="after:absolute after:inset-0">
                    {action.title}
                  </Link>
                </CardTitle>
                <CardDescription className="mt-1.5 flex-1">
                  {action.description}
                </CardDescription>
              </CardBody>
            </Card>
          ))}
        </div>
      </section>
    </div>
  );
}
