"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useCallback, useEffect, useId, useState } from "react";

import { Logo } from "@/components/brand/logo";
import { Icon } from "@/components/ui/icon";
import { cn } from "@/lib/cn";

import { NAV, SURFACE_LABEL, type NavItem, type Surface } from "./nav";

/**
 * The dashboard chrome: fixed sidebar on desktop, off-canvas drawer on mobile.
 *
 * Mobile behaviour is not an afterthought here. Nepal is overwhelmingly
 * mobile-first, and a graduate checking a credential offer is far more likely
 * to be on a mid-range Android phone than a laptop — so the drawer gets real
 * focus management and a real escape hatch, not a CSS-only toggle that traps
 * keyboard users behind an invisible overlay.
 */

export function AppShell({
  surface,
  title,
  account,
  badges,
  children,
}: {
  surface: Surface;
  title: string;
  account?: React.ReactNode;
  badges?: Partial<Record<NonNullable<NavItem["badgeKey"]>, number>>;
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const navId = useId();

  /**
   * The drawer is open *for a route*, not open in the abstract.
   *
   * Navigating changes `pathname`, so `open` becomes false on its own — no
   * effect, and no frame where the drawer is still covering the page the user
   * just tapped through to, which on a phone reads as the tap having done
   * nothing.
   */
  const [openFor, setOpenFor] = useState<string | null>(null);
  const open = openFor === pathname;

  const setOpen = useCallback(
    (next: boolean) => setOpenFor(next ? pathname : null),
    [pathname],
  );

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("keydown", onKey);
    // Stop the page behind the drawer scrolling under the user's finger.
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
  }, [open, setOpen]);

  return (
    <div className="min-h-dvh lg:grid lg:grid-cols-[16rem_1fr]">
      {/* --- desktop sidebar ------------------------------------------------ */}
      <Sidebar
        surface={surface}
        pathname={pathname}
        badges={badges}
        className="hidden lg:flex"
        id={navId}
      />

      {/* --- mobile drawer -------------------------------------------------- */}
      {open && (
        <>
          <div
            className="fixed inset-0 z-40 bg-black/40 lg:hidden"
            onClick={() => setOpen(false)}
            aria-hidden="true"
          />
          <div className="fixed inset-y-0 left-0 z-50 w-64 lg:hidden">
            <Sidebar
              surface={surface}
              pathname={pathname}
              badges={badges}
              className="flex h-full"
              id={`${navId}-mobile`}
              onClose={() => setOpen(false)}
            />
          </div>
        </>
      )}

      <div className="flex min-w-0 flex-col">
        {/* --- top bar ------------------------------------------------------ */}
        <header className="sticky top-0 z-30 flex h-16 items-center gap-3 border-b border-border bg-surface/90 px-4 backdrop-blur sm:px-6">
          <button
            type="button"
            onClick={() => setOpen(true)}
            className="-ml-1 inline-flex size-10 items-center justify-center rounded-[var(--radius-control)] text-text-muted hover:bg-surface-muted lg:hidden"
            aria-label="Open navigation"
            aria-expanded={open}
            aria-controls={`${navId}-mobile`}
          >
            <Icon name="menu" />
          </button>

          <h1 className="min-w-0 flex-1 truncate text-base font-semibold tracking-tight">
            {title}
          </h1>

          {account}
        </header>

        <main id="main" className="flex-1 px-4 py-6 sm:px-6 sm:py-8">
          {children}
        </main>
      </div>
    </div>
  );
}

type Badges = Partial<Record<NonNullable<NavItem["badgeKey"]>, number>>;

/**
 * Optional props are written as `T | undefined` rather than `prop?: T` because
 * `exactOptionalPropertyTypes` is on: under that flag "may be omitted" and "may
 * be explicitly undefined" are different types, and this component is always
 * called by forwarding a value that may itself be undefined.
 */
function Sidebar({
  surface,
  pathname,
  badges,
  className,
  id,
  onClose,
}: {
  surface: Surface;
  pathname: string;
  badges: Badges | undefined;
  className: string | undefined;
  id: string;
  onClose?: () => void;
}) {
  return (
    <nav
      id={id}
      aria-label={SURFACE_LABEL[surface]}
      className={cn("flex-col border-r border-border bg-surface", className)}
    >
      <div className="flex h-16 items-center justify-between gap-2 px-5">
        <Link href="/" className="flex items-center text-brand">
          <Logo size={24} />
        </Link>

        {onClose && (
          <button
            type="button"
            onClick={onClose}
            className="inline-flex size-9 items-center justify-center rounded-[var(--radius-control)] text-text-muted hover:bg-surface-muted"
            aria-label="Close navigation"
          >
            <Icon name="close" size={18} />
          </button>
        )}
      </div>

      <p className="px-5 pt-2 pb-3 text-[0.6875rem] font-semibold tracking-wider text-text-subtle uppercase">
        {SURFACE_LABEL[surface]}
      </p>

      <ul className="flex-1 space-y-0.5 px-3 pb-4">
        {NAV[surface].map((item) => {
          // Exact match for the index route, prefix match for the rest —
          // otherwise "/issuer" stays highlighted on every child page.
          const active =
            item.href === `/${surface}`
              ? pathname === item.href
              : pathname.startsWith(item.href);
          const badge = item.badgeKey ? badges?.[item.badgeKey] : undefined;

          return (
            <li key={item.href}>
              <Link
                href={item.href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "flex items-center gap-3 rounded-[var(--radius-control)] px-3 py-2.5 text-sm transition-colors",
                  active
                    ? "bg-text font-medium text-text-inverted"
                    : "text-text-muted hover:bg-surface-muted hover:text-text",
                )}
              >
                <Icon name={item.icon} size={18} className="shrink-0" />
                <span className="min-w-0 flex-1 truncate">{item.label}</span>
                {badge !== undefined && badge > 0 && (
                  <span
                    className="inline-flex min-w-5 items-center justify-center rounded-full px-1.5 py-0.5 text-[0.6875rem] font-semibold text-white"
                    style={{ backgroundColor: "var(--color-danger)" }}
                  >
                    {badge > 99 ? "99+" : badge}
                    <span className="sr-only"> pending</span>
                  </span>
                )}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
