import { cn } from "@/lib/cn";
import { OUTCOME_META, type VerificationOutcome } from "@/lib/verification";

import { OutcomeGlyph } from "./outcome-icon";

/**
 * The verifier's answer.
 *
 * Two presentations of one data source: a compact chip for tables and lists,
 * and a full panel for the verification result screen. Both read their colour,
 * glyph and copy from `OUTCOME_META`, so a new outcome cannot be added to one
 * and forgotten in the other.
 */

/** Inline token lookup — Tailwind cannot see `bg-${token}-surface` at build time. */
function tokenStyle(token: string) {
  return {
    color: `var(--color-${token})`,
    backgroundColor: `var(--color-${token}-surface)`,
    borderColor: `var(--color-${token}-border)`,
  };
}

export function OutcomeChip({
  outcome,
  className,
}: {
  outcome: VerificationOutcome;
  className?: string;
}) {
  const meta = OUTCOME_META[outcome];

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1",
        "text-xs font-medium whitespace-nowrap",
        className,
      )}
      style={tokenStyle(meta.token)}
    >
      <OutcomeGlyph icon={meta.icon} className="size-3.5 shrink-0" />
      {meta.label}
    </span>
  );
}

export function OutcomePanel({
  outcome,
  detail,
  children,
  className,
}: {
  outcome: VerificationOutcome;
  /** Issuer-supplied context, e.g. a revocation reason. */
  detail?: string;
  children?: React.ReactNode;
  className?: string;
}) {
  const meta = OUTCOME_META[outcome];

  return (
    <section
      className={cn("rounded-[var(--radius-card)] border p-5", className)}
      style={tokenStyle(meta.token)}
      // Announced the moment a result lands. `assertive` because the whole
      // point of the screen is this answer, and a polite region would wait for
      // the user to stop interacting before reading it out.
      role="status"
      aria-live="assertive"
      aria-atomic="true"
    >
      <div className="flex items-start gap-3">
        <span
          className="flex size-10 shrink-0 items-center justify-center rounded-full border"
          style={{ borderColor: "currentColor" }}
        >
          <OutcomeGlyph icon={meta.icon} className="size-5" />
        </span>

        <div className="min-w-0 flex-1">
          {/* The label is the accessible name of the result, so it is a real
              heading rather than styled text — screen-reader users navigate
              results by heading. */}
          <h2 className="text-lg font-semibold tracking-tight">{meta.label}</h2>

          {/* Body copy drops to the standard text colour: the tinted outcome
              colour has enough contrast for a short label but not reliably for
              a paragraph, and legibility beats colour consistency here. */}
          <p className="mt-1 text-sm leading-relaxed text-text">{meta.headline}</p>
          <p className="mt-2 text-sm leading-relaxed text-text-muted">{meta.action}</p>

          {detail && (
            <p className="mt-3 rounded-[var(--radius-control)] bg-surface/60 p-3 text-sm text-text">
              <span className="font-medium">Issuer’s note: </span>
              {detail}
            </p>
          )}

          {children && <div className="mt-4">{children}</div>}
        </div>
      </div>
    </section>
  );
}
