/**
 * Employer verification plans — single source of truth for the pricing shown
 * anywhere in the app.
 *
 * ## Who pays, and why only them
 *
 * Citizens are free forever. Institutions are free forever. Both are the supply
 * side: charging a university to publish degrees, or a graduate to hold their
 * own, would strangle the network before it had one. Only *verification volume*
 * is metered, because that is the only place value is consumed rather than
 * created.
 *
 * ## Why 50 free verifications
 *
 * A Nepali SME hires perhaps two or three people a month, each presenting a
 * couple of documents, so genuine casual use lands around 6–10 lookups. Fifty
 * covers that several times over, which is the point at this stage: the
 * constraint on the network is employers who have never verified anything, not
 * employers verifying too much. A free tier that runs out during the first
 * month of use teaches people the product is a paywall before it has taught
 * them it works.
 *
 * The trade is real and worth stating plainly — at 50, a firm hiring a dozen
 * people a month never reaches the paid tier. That is a deliberate acquisition
 * cost, not an oversight, and it is the number to revisit first once employers
 * are actually converting.
 *
 * This figure must equal `FREE_PLAN_MONTHLY_LOOKUPS` in the backend settings.
 * It is what the server meters against; a mismatch here does not change the
 * limit, it only makes the quota meter lie about it. All three definitions —
 * this constant, the Django setting, and `Subscription.monthly_lookup_limit`'s
 * column default — say 50.
 *
 * Issuing experience letters — a company confirming someone's own employment
 * history — is never metered, on either plan. Only checking other people's
 * documents draws from the quota.
 *
 * ## Why NPR 999
 *
 * Deliberately under the NPR 1,000 threshold, which in practice is the line
 * below which a Kathmandu office manager approves an expense without escalating
 * it. It is roughly an hour of a mid-level salary — trivially justified against
 * the days of phone calls and physical campus visits that verifying one degree
 * costs today.
 *
 * The strategy is volume, not margin per seat. A thousand employers at NPR 999
 * is a real business in this market; fifty employers at NPR 20,000 is not,
 * because fifty employers is not a network.
 *
 * ## Anonymous verification stays free
 *
 * A recruiter scanning a QR code on a printed certificate is never metered —
 * they are rate-limited instead. Quota applies only to authenticated employer
 * lookups, so a candidate sharing their own link can never silently burn an
 * employer's allowance. This mirrors `VerificationLog.counts_against_quota`.
 */

export type PlanId = "COMMUNITY" | "PROFESSIONAL" | "ENTERPRISE";

export interface Plan {
  id: PlanId;
  name: string;
  /** Monthly price in paisa, to avoid float arithmetic on money. */
  monthlyPaisa: number;
  /** Annual price in paisa. Two months free versus paying monthly. */
  annualPaisa: number;
  /** Verifications included per calendar month. `null` means unlimited. */
  monthlyLookups: number | null;
  tagline: string;
  features: readonly string[];
}

/**
 * Three tiers for the demo. `ENTERPRISE` has no self-serve checkout — it is
 * "contact us" pricing everywhere real SaaS products sell it, so its price is
 * left as `null` and the UI shows "Custom" instead of a figure.
 */
export const PLANS: Record<PlanId, Plan> = {
  COMMUNITY: {
    id: "COMMUNITY",
    name: "Community",
    monthlyPaisa: 0,
    annualPaisa: 0,
    monthlyLookups: 50,
    tagline: "For occasional hiring. No card required.",
    features: [
      "50 validity checks per month",
      "Full result detail — not just pass or fail",
      "Unlimited free QR scans of shared certificates",
      "Unlimited experience-letter issuing, always",
      "Verification history for 90 days",
    ],
  },
  PROFESSIONAL: {
    id: "PROFESSIONAL",
    name: "Professional",
    monthlyPaisa: 99_900,
    annualPaisa: 999_000,
    monthlyLookups: null,
    tagline: "For teams hiring every month.",
    features: [
      "Unlimited validity checks",
      "Unlimited experience-letter issuing, always",
      "Bulk verification from a spreadsheet",
      "Team seats — everyone in HR, one subscription",
      "Full verification history and export",
      "Priority support in Nepali and English",
    ],
  },
  ENTERPRISE: {
    id: "ENTERPRISE",
    name: "Enterprise",
    monthlyPaisa: 0,
    annualPaisa: 0,
    monthlyLookups: null,
    tagline: "For large HR teams and staffing agencies.",
    features: [
      "Everything in Professional",
      "Dedicated account manager",
      "Custom integrations (ATS, HRIS)",
      "SSO and audit-log export",
      "SLA-backed uptime and support",
    ],
  },
} as const;

/** Enterprise is quote-based, so nothing in `formatNpr` applies to it. */
export function isCustomPriced(id: PlanId): boolean {
  return id === "ENTERPRISE";
}

/**
 * The backend has two tiers; this file has three. That is not drift — it is
 * pricing presentation over a billing model.
 *
 * `Subscription.plan` is FREE or PRO, and it is what actually meters
 * verifications. COMMUNITY and PROFESSIONAL are those two under the names the
 * pricing page uses. ENTERPRISE is PRO plus a contract nobody can sign
 * self-serve, so it maps onto the same server-side tier and is never something
 * the "upgrade" button can select.
 *
 * Keeping the mapping in one pair of functions is what stops a fourth marketing
 * tier from silently becoming an unmetered account.
 */
export type BackendPlan = "FREE" | "PRO";

export function planIdFor(plan: BackendPlan | undefined): PlanId {
  return plan === "PRO" ? "PROFESSIONAL" : "COMMUNITY";
}

export function backendPlanFor(id: PlanId): BackendPlan {
  return id === "COMMUNITY" ? "FREE" : "PRO";
}

/** First day of next month, when a free allowance resets. */
export function nextResetDate(from: Date = new Date()): Date {
  return new Date(from.getFullYear(), from.getMonth() + 1, 1);
}

/**
 * Format paisa as Nepali rupees.
 *
 * The locale is `ne-NP-u-nu-latn`, not plain `ne-NP`. Plain `ne-NP` renders
 * digits in Devanagari — रू ९९९ — which is technically correct and wrong in
 * practice for three reasons: prices in Nepal are overwhelmingly written in
 * Arabic numerals (Nagarik App included), the figure would clash with every
 * other tabular number in this UI, and a price nobody can skim is a price
 * nobody evaluates.
 *
 * The `-u-nu-latn` extension keeps the नेरू symbol and South Asian digit
 * grouping (1,00,000 rather than 100,000) while forcing Latin numerals.
 *
 * The fallback exists because older Android WebViews — a large share of the
 * target install base — ship incomplete ICU data and can throw on the
 * extension.
 */
export function formatNpr(paisa: number): string {
  const rupees = paisa / 100;
  try {
    return new Intl.NumberFormat("ne-NP-u-nu-latn", {
      style: "currency",
      currency: "NPR",
      maximumFractionDigits: 0,
    }).format(rupees);
  } catch {
    return `रू ${rupees.toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;
  }
}
