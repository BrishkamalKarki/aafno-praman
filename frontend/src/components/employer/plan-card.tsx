import { Button } from "@/components/ui/button";
import { Icon, type IconName } from "@/components/ui/icon";
import { cn } from "@/lib/cn";
import { formatNpr, isCustomPriced, type Plan } from "@/lib/plans";

const PLAN_ICON: Record<Plan["id"], IconName> = {
  COMMUNITY: "user",
  PROFESSIONAL: "shield-check",
  ENTERPRISE: "building",
};

export function PlanCard({
  plan,
  isCurrent,
  onSelect,
  loading = false,
}: {
  plan: Plan;
  isCurrent: boolean;
  /** Omitted for Enterprise, which is "contact us" rather than one click. */
  onSelect?: () => void;
  loading?: boolean;
}) {
  return (
    <div
      className={cn(
        "flex h-full flex-col rounded-[var(--radius-card)] border p-5",
        isCurrent ? "border-brand bg-brand-subtle" : "border-border bg-surface",
      )}
    >
      <div className="flex items-center gap-2.5">
        <span
          className={cn(
            "flex size-9 shrink-0 items-center justify-center rounded-full",
            isCurrent ? "bg-white/60 text-brand" : "bg-surface-muted text-text-subtle",
          )}
        >
          <Icon name={PLAN_ICON[plan.id]} size={17} />
        </span>
        <h3 className="text-base font-semibold tracking-tight">{plan.name}</h3>
        {isCurrent && (
          <span className="ml-auto rounded-full border border-brand-border bg-surface px-2 py-0.5 text-xs font-medium text-brand">
            Current plan
          </span>
        )}
      </div>

      <p className="mt-3">
        {isCustomPriced(plan.id) ? (
          <span className="text-2xl font-semibold tracking-tight">Custom</span>
        ) : plan.monthlyPaisa === 0 ? (
          <span className="text-2xl font-semibold tracking-tight">Free</span>
        ) : (
          <>
            <span className="text-2xl font-semibold tracking-tight">
              {formatNpr(plan.monthlyPaisa)}
            </span>
            <span className="text-sm text-text-muted"> / month</span>
          </>
        )}
      </p>
      <p className="mt-1 text-sm text-text-muted">{plan.tagline}</p>

      <ul className="mt-4 flex-1 space-y-2 text-sm">
        {plan.features.map((feature) => (
          <li key={feature} className="flex items-start gap-2">
            <Icon name="shield-check" size={15} className="mt-0.5 shrink-0 text-brand" />
            <span>{feature}</span>
          </li>
        ))}
      </ul>

      <div className="mt-5">
        {isCurrent ? (
          <Button variant="secondary" fullWidth disabled>
            Current plan
          </Button>
        ) : plan.id === "ENTERPRISE" ? (
          <a href="mailto:sales@aafnopraman.com.np">
            <Button variant="secondary" fullWidth>
              Contact sales
            </Button>
          </a>
        ) : (
          <Button fullWidth loading={loading} onClick={onSelect}>
            Upgrade to {plan.name}
          </Button>
        )}
      </div>
    </div>
  );
}
