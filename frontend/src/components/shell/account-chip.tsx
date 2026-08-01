"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { Icon } from "@/components/ui/icon";
import { useAuth } from "@/lib/auth/auth-context";

/**
 * Identity indicator in the top bar, and the only way out of the app.
 *
 * Shows the signed-in email, because email is the primary login for every role
 * on this platform. The address chip beside it appears only where an on-chain
 * identity is actually in use — see `IssuerAccountChip`. Citizens and employers
 * never hold one and never pay gas.
 *
 * The menu is a plain popover rather than a headless-ui dependency: it needs
 * escape-to-close and click-outside for two items, which is twenty lines.
 */
export function AccountChip({
  email,
  wallet,
  subtitle,
}: {
  /** Falls back to the signed-in user, so most callers pass nothing. */
  email?: string;
  wallet?: string;
  /** Organisation name or role, shown under the address in the menu. */
  subtitle?: string;
}) {
  const { user, logout } = useAuth();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const address = email ?? user?.email ?? "";

  useEffect(() => {
    if (!open) return;

    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    const onPointerDown = (event: MouseEvent) => {
      if (!containerRef.current?.contains(event.target as Node)) setOpen(false);
    };

    document.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onPointerDown);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", onPointerDown);
    };
  }, [open]);

  function handleSignOut() {
    logout();
    // `replace`, not `push`: the back button must not return to a dashboard that
    // would only bounce them here again.
    router.replace("/login");
  }

  return (
    <div className="relative flex items-center gap-2" ref={containerRef}>
      {wallet && (
        <span className="hidden items-center gap-2 rounded-full border border-border bg-surface-muted py-1 pr-1 pl-3 text-xs sm:inline-flex">
          <span className="font-medium text-text">Issuer key</span>
          <span className="inline-flex items-center gap-1.5 rounded-full bg-surface px-2 py-1 font-mono text-text-muted">
            <Icon name="wallet" size={13} />
            {shorten(wallet)}
          </span>
        </span>
      )}

      <button
        type="button"
        onClick={() => setOpen((current) => !current)}
        className="inline-flex items-center gap-2 rounded-full border border-border py-1 pr-2.5 pl-1 text-sm hover:bg-surface-muted"
        aria-label={`Account menu for ${address}`}
        aria-expanded={open}
        aria-haspopup="menu"
      >
        <span
          className="flex size-7 items-center justify-center rounded-full text-xs font-semibold text-white"
          style={{ backgroundColor: "var(--color-brand)" }}
          aria-hidden="true"
        >
          {address.charAt(0).toUpperCase() || "?"}
        </span>
        <span className="hidden max-w-40 truncate text-text-muted sm:inline">{address}</span>
        <Icon name="chevron-down" size={14} className="text-text-subtle" />
      </button>

      {open && (
        <div
          role="menu"
          className="absolute top-full right-0 z-40 mt-2 w-64 overflow-hidden rounded-[var(--radius-card)] border border-border bg-surface shadow-[var(--shadow-raised)]"
        >
          <div className="border-b border-border px-4 py-3">
            <p className="truncate text-sm font-medium text-text">{user?.full_name || address}</p>
            <p className="mt-0.5 truncate text-xs text-text-subtle">{address}</p>
            {subtitle && <p className="mt-1 truncate text-xs text-text-muted">{subtitle}</p>}
          </div>

          <button
            type="button"
            role="menuitem"
            onClick={handleSignOut}
            className="flex w-full items-center gap-2 px-4 py-3 text-left text-sm text-text hover:bg-surface-muted"
          >
            <Icon name="logout" size={16} className="text-text-subtle" />
            Sign out
          </button>
        </div>
      )}
    </div>
  );
}

function shorten(address: string): string {
  return address.length > 12 ? `${address.slice(0, 6)}…${address.slice(-4)}` : address;
}
