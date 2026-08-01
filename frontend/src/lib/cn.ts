/**
 * Conditional class name joiner.
 *
 * Deliberately not `clsx` + `tailwind-merge`. Those two packages exist to
 * resolve conflicting Tailwind utilities at runtime, which is only necessary
 * when components accept arbitrary overriding classes. The primitives here
 * expose typed `variant` and `size` props instead, so conflicts are prevented
 * by the API rather than reconciled after the fact — and the app carries two
 * fewer dependencies on its critical rendering path.
 */
export type ClassValue = string | false | null | undefined;

export function cn(...values: ClassValue[]): string {
  return values.filter(Boolean).join(" ");
}
