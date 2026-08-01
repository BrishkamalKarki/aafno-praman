import { Icon } from "@/components/ui/icon";

/**
 * Form field classes, extracted rather than reinvented.
 *
 * Every form in this app already used the same three strings inline. Naming them
 * is not an abstraction so much as a promise that a future field will not be
 * 40px tall while the one beside it is 44 — the touch-target floor is the whole
 * reason the height is fixed.
 */
export const inputClass =
  "mt-1.5 h-11 w-full rounded-[var(--radius-control)] border border-border-strong bg-surface px-3 text-sm";

export const textareaClass =
  "mt-1.5 w-full rounded-[var(--radius-control)] border border-border-strong bg-surface px-3 py-2.5 text-sm";

export const labelClass = "block text-sm font-medium";

/** Filter/search controls, which sit in a row rather than under a label. */
export const filterClass =
  "h-10 rounded-[var(--radius-control)] border border-border-strong bg-surface px-3 text-sm";

/**
 * A file input that can actually be clicked.
 *
 * The forms here originally reused `inputClass` for uploads, which pins the
 * control to `h-11` and adds `px-3 pt-2` on top. A file input is not a text
 * box: the browser lays out a real button plus a filename label inside it, and
 * inside a 44px box already spending 8px on padding the button overflows the
 * border and is clipped — so the visible part of the control is inert and
 * clicking it appears to do nothing.
 *
 * Height is therefore intrinsic, and the `file:` variants style the button the
 * browser draws rather than the box around it.
 */
export const fileInputClass =
  "mt-1.5 block w-full cursor-pointer rounded-[var(--radius-control)] border border-border-strong " +
  "bg-surface p-2.5 text-sm " +
  "file:mr-3 file:cursor-pointer file:rounded file:border-0 file:bg-surface-muted " +
  "file:px-3 file:py-1.5 file:text-sm file:font-medium file:text-text";

export function FileField({
  id,
  label,
  accept,
  optional = false,
  hint,
  file,
  onSelect,
  required = false,
}: {
  id: string;
  label: string;
  accept?: string;
  optional?: boolean;
  hint?: string;
  /** The chosen file, echoed back so the user can see the pick registered. */
  file?: File | null;
  onSelect: (file: File | null) => void;
  required?: boolean;
}) {
  return (
    <div>
      <label htmlFor={id} className={labelClass}>
        {label}
        {optional && <span className="font-normal text-text-subtle"> (optional)</span>}
      </label>
      <input
        id={id}
        type="file"
        required={required}
        {...(accept ? { accept } : {})}
        onChange={(event) => onSelect(event.target.files?.[0] ?? null)}
        className={fileInputClass}
      />
      {hint && <p className="mt-1 text-xs text-text-subtle">{hint}</p>}
      {/* Confirming the selection matters more here than anywhere else in the
          app: a file input that silently kept the previous pick is the bug
          people report as "it did nothing". */}
      {file && (
        <p className="mt-1.5 flex items-center gap-1.5 text-xs text-text-subtle">
          <Icon name="file-text" size={13} className="shrink-0" />
          <span className="truncate">{file.name}</span>
          <button
            type="button"
            onClick={() => onSelect(null)}
            className="ml-1 shrink-0 font-medium text-brand hover:underline"
          >
            Remove
          </button>
        </p>
      )}
    </div>
  );
}

/**
 * An error that blocked the action the user just took.
 *
 * Stays on screen, next to the control, until they do something about it — see
 * `lib/toast.tsx` for why failures are not toasts.
 */
export function FormError({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <p
      role="alert"
      className="rounded-[var(--radius-control)] border px-3 py-2.5 text-sm"
      style={{
        color: "var(--color-danger)",
        backgroundColor: "var(--color-danger-surface)",
        borderColor: "var(--color-danger)",
      }}
    >
      {message}
    </p>
  );
}

/**
 * Placeholder rows while a list loads.
 *
 * Sized to the real rows so the page does not jump when data arrives. Marked
 * `aria-hidden` with a single live-region status alongside — announcing six
 * empty boxes is noise, "Loading" is information.
 */
export function LoadingRows({ rows = 3 }: { rows?: number }) {
  return (
    <>
      <p className="sr-only" role="status">
        Loading…
      </p>
      <div
        className="divide-y divide-border overflow-hidden rounded-[var(--radius-card)] border border-border bg-surface"
        aria-hidden="true"
      >
        {Array.from({ length: rows }).map((_, index) => (
          <div key={index} className="flex items-center gap-3 px-4 py-3.5">
            <div className="min-w-0 flex-1 space-y-2">
              <div className="h-3.5 w-2/5 animate-pulse rounded bg-surface-muted" />
              <div className="h-3 w-3/5 animate-pulse rounded bg-surface-muted" />
            </div>
            <div className="h-5 w-20 animate-pulse rounded-full bg-surface-muted" />
          </div>
        ))}
      </div>
    </>
  );
}

/** Matching placeholder for the four-across stat row. */
export function LoadingStats({ tiles = 4 }: { tiles?: number }) {
  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-4" aria-hidden="true">
      {Array.from({ length: tiles }).map((_, index) => (
        <div
          key={index}
          className="rounded-[var(--radius-card)] border border-border bg-surface p-4"
        >
          <div className="h-3 w-20 animate-pulse rounded bg-surface-muted" />
          <div className="mt-2.5 h-8 w-12 animate-pulse rounded bg-surface-muted" />
        </div>
      ))}
    </div>
  );
}

/**
 * A request that failed, with a way out.
 *
 * Always offers a retry. Most failures here are a backend that has not finished
 * starting or a node that blipped, and "try again" resolves them — telling
 * someone only that something went wrong leaves them reloading the browser.
 */
export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div
      role="alert"
      className="rounded-[var(--radius-card)] border px-5 py-6 text-center"
      style={{
        backgroundColor: "var(--color-danger-surface)",
        borderColor: "var(--color-danger)",
      }}
    >
      <p className="text-sm font-medium" style={{ color: "var(--color-danger)" }}>
        Could not load this
      </p>
      <p className="mx-auto mt-1 max-w-sm text-sm text-text-muted">{message}</p>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="mt-3 text-sm font-medium text-brand hover:underline"
        >
          Try again
        </button>
      )}
    </div>
  );
}
