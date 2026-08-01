import type { IconName } from "@/components/ui/icon";

/**
 * Navigation, declared per surface rather than assembled in each layout.
 *
 * Kept as data so the four consoles cannot drift into different navigation
 * idioms — and so permission filtering happens in one place instead of being
 * re-derived in every sidebar.
 *
 * This is presentation only. Every route behind these links is enforced
 * server-side; a nav item the user should not see is a cosmetic bug, not a
 * security boundary.
 */

export interface NavItem {
  href: string;
  label: string;
  icon: IconName;
  /** Shown as a small count bubble, e.g. pending credential confirmations. */
  badgeKey?: "pendingOffers";
}

export type Surface = "citizen" | "issuer" | "employer" | "admin";

export const NAV: Record<Surface, readonly NavItem[]> = {
  citizen: [
    { href: "/citizen", label: "Dashboard", icon: "grid" },
    { href: "/citizen/credentials", label: "My credentials", icon: "shield-check" },
    { href: "/citizen/shares/new", label: "Share a credential", icon: "link" },
    // The seeker-claim half of issuance: for a job whose employer never sent a
    // letter. Without an entry point here the employer's review inbox has
    // nothing that can ever reach it.
    { href: "/citizen/claims/new", label: "Log a past job", icon: "inbox" },
    { href: "/citizen/access-log", label: "Who checked me", icon: "activity" },
    { href: "/citizen/profile", label: "Account", icon: "user" },
  ],
  issuer: [
    { href: "/issuer", label: "Dashboard", icon: "grid" },
    { href: "/issuer/issue", label: "Issue single", icon: "plus" },
    { href: "/issuer/bulk", label: "Bulk issue", icon: "upload" },
    { href: "/issuer/history", label: "History", icon: "clock" },
    { href: "/issuer/activity", label: "Ledger activity", icon: "activity" },
    { href: "/issuer/organization", label: "Organisation", icon: "building" },
  ],
  employer: [
    { href: "/employer", label: "Dashboard", icon: "grid" },
    { href: "/employer/verify", label: "Check validity", icon: "shield-check" },
    { href: "/employer/issue-experience", label: "Issue experience letter", icon: "upload" },
    { href: "/employer/bulk-issue-experience", label: "Bulk issue", icon: "grid" },
    // Claims run the other way to issuance: an ex-employee asserts, this
    // company confirms. Badged because an unreviewed claim blocks a real person.
    {
      href: "/employer/claims",
      label: "Claims to review",
      icon: "inbox",
      badgeKey: "pendingOffers",
    },
    { href: "/employer/candidates", label: "Find candidates", icon: "search" },
    { href: "/employer/history", label: "History", icon: "clock" },
    { href: "/employer/billing", label: "Plan & usage", icon: "activity" },
    { href: "/employer/organization", label: "Organisation", icon: "building" },
  ],
  admin: [
    { href: "/admin", label: "Dashboard", icon: "grid" },
    {
      href: "/admin/organizations",
      label: "Organisations",
      icon: "shield-check",
      badgeKey: "pendingOffers",
    },
    { href: "/admin/create/user", label: "Create user", icon: "user" },
    { href: "/admin/create/company", label: "Create company", icon: "building" },
    { href: "/admin/create/institution", label: "Create institution", icon: "building" },
  ],
} as const;

export const SURFACE_LABEL: Record<Surface, string> = {
  citizen: "My credentials",
  issuer: "Issuer console",
  employer: "Employer console",
  admin: "Admin console",
};
