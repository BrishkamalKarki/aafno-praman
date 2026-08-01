import Link from "next/link";

import { Icon, type IconName } from "@/components/ui/icon";
import { cn } from "@/lib/cn";

/**
 * Dashboard building blocks, shared by all four surfaces.
 *
 * The visual language is deliberately quiet: flat surfaces, one accent, generous
 * whitespace, no gradients or decorative illustration. Two reasons.
 *
 * First, this is trust infrastructure. A page that looks like a marketing site
 * undermines the claim it is making — government and university staff read
 * visual restraint as seriousness.
 *
 * Second, Nagarik App set the expectation for what a Nepali public-service
 * interface looks like: large tappable tiles, plain labels, high contrast, and
 * no chrome competing with the content. Users arriving here have used that app;
 * matching its idiom means they already know how this one works.
 */

/* -------------------------------------------------------------- stat tiles */

export function StatGrid({ children }: { children: React.ReactNode }) {
  return (
    <dl className="grid grid-cols-2 gap-3 lg:grid-cols-4">{children}</dl>
  );
}

export function StatTile({
  label,
  value,
  tone = "neutral",
  hint,
}: {
  label: string;
  value: number | string;
  tone?: "neutral" | "verified" | "revoked" | "brand";
  hint?: string;
}) {
  const tones: Record<string, string> = {
    neutral: "var(--color-text)",
    verified: "var(--color-verified)",
    revoked: "var(--color-revoked)",
    brand: "var(--color-brand)",
  };

  return (
    <div className="rounded-[var(--radius-card)] border border-border bg-surface p-4">
      {/* dt before dd in the markup so a screen reader reads "Total issued, 8"
          rather than an unlabelled number. The visual order is unchanged. */}
      <dt className="text-xs font-medium text-text-muted">{label}</dt>
      <dd
        className="mt-1.5 text-3xl font-semibold tabular-nums tracking-tight"
        style={{ color: tones[tone] }}
      >
        {value}
      </dd>
      {hint && <p className="mt-1 text-xs text-text-subtle">{hint}</p>}
    </div>
  );
}

/* ------------------------------------------------------------ action tiles */

/**
 * The Nagarik-style quick action: a large, obvious, single-purpose target.
 *
 * Minimum height is 56px rather than the 44px WCAG floor. These are the primary
 * actions on the page and are frequently used one-handed on a phone, where the
 * extra margin is the difference between confident and fiddly.
 */
export function ActionGrid({ children }: { children: React.ReactNode }) {
  return <div className="grid gap-3 sm:grid-cols-2">{children}</div>;
}

export function ActionTile({
  href,
  label,
  description,
  icon,
  primary = false,
}: {
  href: string;
  label: string;
  description?: string;
  icon: IconName;
  primary?: boolean;
}) {
  return (
    <Link
      href={href}
      className={cn(
        "group flex min-h-14 items-center gap-3 rounded-[var(--radius-card)] border px-4 py-3.5 transition-colors",
        primary
          ? "border-transparent bg-text text-text-inverted hover:opacity-90"
          : "border-border bg-surface text-text hover:border-brand-border hover:bg-surface-muted",
      )}
    >
      <span
        className={cn(
          "flex size-9 shrink-0 items-center justify-center rounded-full",
          primary ? "bg-white/15" : "bg-brand-subtle text-brand",
        )}
      >
        <Icon name={icon} size={18} />
      </span>

      <span className="min-w-0 flex-1">
        <span className="block text-sm font-medium">{label}</span>
        {description && (
          <span
            className={cn(
              "mt-0.5 block text-xs",
              primary ? "text-white/70" : "text-text-muted",
            )}
          >
            {description}
          </span>
        )}
      </span>

      <Icon
        name="chevron-right"
        size={16}
        className={cn("shrink-0", primary ? "text-white/60" : "text-text-subtle")}
      />
    </Link>
  );
}

/* ------------------------------------------------------------ list sections */

export function SectionHeader({
  title,
  href,
  linkLabel = "View all",
}: {
  title: string;
  href?: string;
  linkLabel?: string;
}) {
  return (
    <div className="mb-3 flex items-baseline justify-between gap-3">
      <h2 className="text-sm font-semibold tracking-tight">{title}</h2>
      {href && (
        <Link
          href={href}
          className="inline-flex items-center gap-0.5 text-xs font-medium text-brand hover:underline"
        >
          {/* The visible text is generic, so the accessible name gets the
              section title appended — otherwise a screen reader lists four
              identical "View all" links with no way to tell them apart. */}
          {linkLabel}
          <span className="sr-only"> {title.toLowerCase()}</span>
          <Icon name="chevron-right" size={14} />
        </Link>
      )}
    </div>
  );
}

export function ListCard({ children }: { children: React.ReactNode }) {
  return (
    <ul className="divide-y divide-border overflow-hidden rounded-[var(--radius-card)] border border-border bg-surface">
      {children}
    </ul>
  );
}

export function ListRow({
  title,
  subtitle,
  meta,
  trailing,
  href,
}: {
  title: string;
  subtitle?: string;
  meta?: string;
  trailing?: React.ReactNode;
  href?: string;
}) {
  const body = (
    <div className="flex items-center gap-3 px-4 py-3">
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium text-text">{title}</p>
        {subtitle && (
          <p className="break-hash mt-0.5 font-mono text-xs text-text-subtle">{subtitle}</p>
        )}
        {meta && <p className="mt-0.5 text-xs text-text-subtle">{meta}</p>}
      </div>
      {trailing}
    </div>
  );

  return (
    <li>
      {href ? (
        <Link href={href} className="block hover:bg-surface-muted">
          {body}
        </Link>
      ) : (
        body
      )}
    </li>
  );
}

export function EmptyState({
  icon,
  title,
  description,
  action,
}: {
  icon: IconName;
  title: string;
  description: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="rounded-[var(--radius-card)] border border-dashed border-border-strong bg-surface px-6 py-10 text-center">
      <span className="mx-auto flex size-11 items-center justify-center rounded-full bg-surface-muted text-text-subtle">
        <Icon name={icon} size={20} />
      </span>
      <p className="mt-3 text-sm font-medium text-text">{title}</p>
      <p className="mx-auto mt-1 max-w-sm text-sm text-text-muted">{description}</p>
      {action && <div className="mt-4 flex justify-center">{action}</div>}
    </div>
  );
}

/* ------------------------------------------------------------ status pills */

export type RecordState =
  | "ACTIVE"
  | "PENDING"
  | "AWAITING_CONFIRMATION"
  | "DECLINED"
  | "REVOKED";

const STATE_META: Record<RecordState, { label: string; token: string }> = {
  ACTIVE: { label: "Active", token: "verified" },
  PENDING: { label: "Anchoring", token: "superseded" },
  AWAITING_CONFIRMATION: { label: "Awaiting confirmation", token: "revoked" },
  DECLINED: { label: "Declined", token: "notfound" },
  REVOKED: { label: "Revoked", token: "tampered" },
};

export function StatusPill({ state }: { state: RecordState }) {
  const meta = STATE_META[state];
  return (
    <span
      className="inline-flex shrink-0 items-center gap-1.5 rounded-full border px-2 py-0.5 text-xs font-medium whitespace-nowrap"
      style={{
        color: `var(--color-${meta.token})`,
        backgroundColor: `var(--color-${meta.token}-surface)`,
        borderColor: `var(--color-${meta.token}-border)`,
      }}
    >
      {/* A dot alone would carry meaning in colour only. It is decorative here;
          the adjacent label is what conveys the state. */}
      <span
        className="size-1.5 rounded-full bg-current"
        aria-hidden="true"
      />
      {meta.label}
    </span>
  );
}
