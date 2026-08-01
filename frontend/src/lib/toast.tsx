"use client";

/**
 * Transient notifications.
 *
 * Success is the only thing announced this way. Errors that block an action stay
 * inline next to the control that failed — a toast that disappears after four
 * seconds is the wrong place for "your credential was not issued, and here is
 * why", and users on a phone frequently never see one at all.
 *
 * The region is `aria-live="polite"` rather than `assertive`: a confirmation is
 * not worth interrupting whatever a screen reader is mid-sentence on.
 */

import { createContext, useCallback, useContext, useMemo, useState } from "react";

import { Icon, type IconName } from "@/components/ui/icon";

export type ToastTone = "success" | "danger" | "info";

interface Toast {
  id: string;
  tone: ToastTone;
  message: string;
}

interface ToastContextValue {
  notify: (message: string, tone?: ToastTone) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

/**
 * Reuses the existing outcome tokens and the existing icon set rather than
 * introducing a third palette or three new glyphs for four seconds of screen
 * time.
 */
const TONE: Record<ToastTone, { token: string; icon: IconName }> = {
  success: { token: "verified", icon: "shield-check" },
  danger: { token: "tampered", icon: "close" },
  info: { token: "superseded", icon: "inbox" },
};

const DISMISS_AFTER_MS = 4500;

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const notify = useCallback((message: string, tone: ToastTone = "info") => {
    const id = `${Date.now()}-${Math.random().toString(36).slice(2)}`;
    setToasts((current) => [...current, { id, tone, message }]);
    window.setTimeout(() => {
      setToasts((current) => current.filter((toast) => toast.id !== id));
    }, DISMISS_AFTER_MS);
  }, []);

  const value = useMemo(() => ({ notify }), [notify]);

  return (
    <ToastContext.Provider value={value}>
      {children}

      <div
        className="pointer-events-none fixed inset-x-0 bottom-4 z-50 flex flex-col items-center gap-2 px-4 sm:inset-x-auto sm:right-4 sm:items-end"
        aria-live="polite"
      >
        {toasts.map((toast) => {
          const tone = TONE[toast.tone];
          return (
            <div
              key={toast.id}
              role="status"
              className="pointer-events-auto flex max-w-sm items-start gap-2 rounded-[var(--radius-card)] border px-4 py-3 text-sm shadow-[var(--shadow-raised)]"
              style={{
                color: `var(--color-${tone.token})`,
                backgroundColor: `var(--color-${tone.token}-surface)`,
                borderColor: `var(--color-${tone.token}-border)`,
              }}
            >
              <Icon name={tone.icon} size={16} className="mt-0.5 shrink-0" />
              <span className="text-text">{toast.message}</span>
            </div>
          );
        })}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastContextValue {
  const context = useContext(ToastContext);
  if (!context) throw new Error("useToast must be used inside <ToastProvider>.");
  return context;
}
