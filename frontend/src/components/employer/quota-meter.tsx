import Link from "next/link";

import { PLANS, formatNpr, nextResetDate, type PlanId } from "@/lib/plans";

/**
 * Remaining verification allowance.
 *
 * Designed to be honest rather than pushy. An employer who discovers their
 * quota by hitting a paywall mid-hire will not upgrade — they will assume the
 * platform is unreliable and go back to phoning the university. So the meter is
 * always visible, always states the reset date, and only turns into an upgrade
 * prompt once the allowance is genuinely nearly gone.
 *
 * `limit` and `resetsAt` come from `/verify/quota/` when they are passed, and
 * they take precedence over the figures in `lib/plans.ts`. Those constants
 * describe what the pricing page *offers*; the server describes what this
 * organisation is actually metered against, and a meter showing anything but the
 * number that will block the next lookup is a meter that lies.
 */

const WARN_AT = 0.7;
const CRITICAL_AT = 0.9;

export function QuotaMeter({
  plan,
  used,
  limit: serverLimit,
  resetsAt,
  compact = false,
}: {
  plan: PlanId;
  used: number;
  /** Server-reported cap. `null` means unlimited. Omit to fall back to the plan. */
  limit?: number | null;
  /** ISO instant the allowance resets. Omit to compute the first of next month. */
  resetsAt?: string;
  compact?: boolean;
}) {
  const limit = serverLimit === undefined ? PLANS[plan].monthlyLookups : serverLimit;

  if (limit === null || limit === 0) {
    return (
      <div className="rounded-[var(--radius-card)] border border-border bg-surface p-4">
        <p className="text-sm font-medium">Unlimited verifications</p>
        <p className="mt-1 text-xs text-text-muted">
          {PLANS[plan].name} plan — no monthly cap.
        </p>
      </div>
    );
  }

  const remaining = Math.max(0, limit - used);
  const ratio = Math.min(1, used / limit);
  const token =
    ratio >= CRITICAL_AT ? "tampered" : ratio >= WARN_AT ? "revoked" : "verified";

  const resets = (resetsAt ? new Date(resetsAt) : nextResetDate()).toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
  });

  return (
    <div className="rounded-[var(--radius-card)] border border-border bg-surface p-4">
      <div className="flex items-baseline justify-between gap-3">
        <p className="text-sm font-medium">
          <span className="tabular-nums">{remaining}</span> of{" "}
          <span className="tabular-nums">{limit}</span> left
        </p>
        <p className="text-xs text-text-subtle">Resets {resets}</p>
      </div>

      {/* Native progress element: it is announced correctly, works without CSS,
          and needs no ARIA to be understood. The bar below is purely visual. */}
      <progress
        value={used}
        max={limit}
        className="sr-only"
      >
        {used} of {limit} verifications used
      </progress>
      <div
        className="mt-2.5 h-1.5 overflow-hidden rounded-full bg-surface-muted"
        aria-hidden="true"
      >
        <div
          className="h-full rounded-full transition-[width]"
          style={{
            width: `${Math.max(2, ratio * 100)}%`,
            backgroundColor: `var(--color-${token})`,
          }}
        />
      </div>

      {!compact && ratio >= WARN_AT && (
        <div className="mt-3 border-t border-border pt-3">
          <p className="text-xs text-text-muted">
            {remaining === 0
              ? "You have used this month’s free verifications."
              : `Only ${remaining} left this month.`}{" "}
            {PLANS.PROFESSIONAL.name} is unlimited for{" "}
            {formatNpr(PLANS.PROFESSIONAL.monthlyPaisa)}/month.
          </p>
          <Link
            href="/employer/billing"
            className="mt-2 inline-block text-xs font-medium text-brand hover:underline"
          >
            See plans
          </Link>
        </div>
      )}
    </div>
  );
}
