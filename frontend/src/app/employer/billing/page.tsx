"use client";

import { useState } from "react";

import { PlanCard } from "@/components/employer/plan-card";
import { QuotaMeter } from "@/components/employer/quota-meter";
import { ErrorState, LoadingStats } from "@/components/ui/form";
import { errorMessage } from "@/lib/api/errors";
import { useChangePlan, useQuota, useSubscription } from "@/lib/api/hooks";
import { backendPlanFor, planIdFor, PLANS, type PlanId } from "@/lib/plans";
import { useToast } from "@/lib/toast";

/**
 * Plan & usage — demo mode, but not a fake.
 *
 * No payment provider is wired up: no Stripe, no Khalti, no eSewa. What is real
 * is everything downstream of one. The plan lives on `Subscription`, switching
 * it is a genuine `PATCH` that moves `monthly_lookup_limit`, and the very next
 * verification is metered against the new number. Usage on this page is what the
 * server has actually counted, not a local tally.
 *
 * The earlier version kept the plan in `localStorage`, which looked identical
 * and meant nothing: the quota never moved, so "Professional" was a label on a
 * still-limited account. What is missing here is the money, and the page says so
 * rather than miming a checkout.
 */
export default function BillingPage() {
  const subscription = useSubscription();
  const quota = useQuota();
  const changePlan = useChangePlan();
  const { notify } = useToast();

  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState<PlanId | null>(null);

  const current = planIdFor(subscription.data?.plan);

  async function select(id: PlanId) {
    if (id === current) return;
    setError(null);
    setPending(id);
    try {
      await changePlan.mutateAsync(backendPlanFor(id));
      notify(`Switched to ${PLANS[id].name}.`, "success");
    } catch (caught) {
      setError(errorMessage(caught, "Could not change the plan."));
    } finally {
      setPending(null);
    }
  }

  return (
    <div className="mx-auto w-full max-w-5xl space-y-8">
      <div>
        <h1 className="text-lg font-semibold tracking-tight">Plan &amp; usage</h1>
        <p className="mt-1.5 max-w-xl text-sm text-text-muted">
          {subscription.isPending ? (
            "Loading your plan…"
          ) : (
            <>
              You&apos;re on the{" "}
              <span className="font-medium text-text">{PLANS[current].name}</span> plan.
            </>
          )}
        </p>
      </div>

      {error && (
        <ErrorState message={error} onRetry={() => void subscription.refetch()} />
      )}

      <div className="max-w-sm">
        {quota.isPending ? (
          <LoadingStats tiles={1} />
        ) : (
          <QuotaMeter
            plan={current}
            used={quota.data?.used ?? 0}
            limit={quota.data?.limit ?? null}
            {...(quota.data?.resets_at ? { resetsAt: quota.data.resets_at } : {})}
            compact
          />
        )}
      </div>

      <section aria-labelledby="plans">
        <h2 id="plans" className="mb-3 text-sm font-semibold tracking-tight">
          Plans
        </h2>
        <div className="grid gap-4 sm:grid-cols-3">
          <PlanCard
            plan={PLANS.COMMUNITY}
            isCurrent={current === "COMMUNITY"}
            loading={pending === "COMMUNITY"}
            onSelect={() => void select("COMMUNITY")}
          />
          <PlanCard
            plan={PLANS.PROFESSIONAL}
            isCurrent={current === "PROFESSIONAL"}
            loading={pending === "PROFESSIONAL"}
            onSelect={() => void select("PROFESSIONAL")}
          />
          {/* Enterprise has no self-serve path anywhere real SaaS sells it, and
              it maps onto the same server-side tier as Professional — so there
              is nothing here for a button to do. */}
          <PlanCard plan={PLANS.ENTERPRISE} isCurrent={false} />
        </div>

        <p className="mt-4 text-xs text-text-subtle">
          Demo mode — no card is charged and no invoice is raised. The plan change itself is
          real: your monthly verification limit moves with it immediately.
        </p>
      </section>
    </div>
  );
}
