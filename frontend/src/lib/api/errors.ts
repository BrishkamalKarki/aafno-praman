import { ApiError } from "@/lib/api/client";

/**
 * Turn anything thrown into one line a person can act on.
 *
 * DRF returns field errors as `details: { field: ["message"] }`, and the
 * top-level `message` for those is the generic "Validation failed." Showing that
 * tells a registrar nothing, so the first field error is surfaced instead — it
 * is almost always the one thing they need to change.
 */
export function errorMessage(error: unknown, fallback = "Something went wrong."): string {
  if (error instanceof ApiError) {
    const field = firstFieldError(error.details);
    return field ?? error.message;
  }
  if (error instanceof Error && error.message) return error.message;
  return fallback;
}

function firstFieldError(details: Record<string, unknown>): string | null {
  for (const value of Object.values(details)) {
    if (typeof value === "string" && value.trim()) return value;
    if (Array.isArray(value)) {
      const first = value.find((entry) => typeof entry === "string" && entry.trim());
      if (typeof first === "string") return first;
    }
    // Nested serializers (`detail: { end_date: [...] }`) arrive one level down.
    if (value && typeof value === "object") {
      const nested = firstFieldError(value as Record<string, unknown>);
      if (nested) return nested;
    }
  }
  return null;
}

/** DRF's pagination envelope, which every list endpoint here uses. */
export interface Paginated<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

/**
 * Read a list response whether or not it is paginated.
 *
 * Some endpoints in this API paginate and some return a bare array; a helper is
 * cheaper than remembering which is which at twenty call sites.
 */
export function listOf<T>(payload: Paginated<T> | T[] | undefined | null): T[] {
  if (!payload) return [];
  return Array.isArray(payload) ? payload : (payload.results ?? []);
}
