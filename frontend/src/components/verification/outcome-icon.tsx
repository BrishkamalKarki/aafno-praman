import type { OutcomeIcon } from "@/lib/verification";

/**
 * Outcome glyphs.
 *
 * Seven silhouettes that stay distinguishable at 16px and in greyscale. Shape
 * carries the meaning; colour only reinforces it. Inline SVG rather than an
 * icon package because seven paths do not justify a dependency, and because
 * hand-drawn paths can be tuned for legibility at chip size — which generic
 * icon sets are not.
 */

const PATHS: Record<OutcomeIcon, React.ReactNode> = {
  // Seal with a tick — the only "pass" shape in the set.
  "check-seal": (
    <>
      <path d="M12 2.5 14.4 5l3.4-.2.5 3.4 2.7 2.1-1.6 3 1.6 3-2.7 2.1-.5 3.4-3.4-.2L12 21.5 9.6 19l-3.4.2-.5-3.4L3 13.7l1.6-3L3 7.7l2.7-2.1.5-3.4L9.6 5 12 2.5Z" />
      <path d="m8.75 12 2.25 2.25L15.5 9.75" strokeWidth="2.25" />
    </>
  ),
  // Torn page — a document whose contents no longer hold together.
  "broken-doc": (
    <>
      <path d="M6 3h7l5 5v13H6z" />
      <path d="M13 3v5h5" />
      <path d="m9.5 11.5 2.5 2-2.5 2 2.5 2" strokeWidth="1.75" />
    </>
  ),
  // Person with a stroke through — genuine record, wrong holder.
  "person-slash": (
    <>
      <circle cx="12" cy="8" r="3.25" />
      <path d="M5.5 20a6.5 6.5 0 0 1 13 0" />
      <path d="M4 20 20 4" strokeWidth="2.25" />
    </>
  ),
  // Raised palm — an authority stopping it, not a defect in the document.
  "hand-stop": (
    <>
      <path d="M9 11V4.75a1.25 1.25 0 0 1 2.5 0V11" />
      <path d="M11.5 10.5V3.75a1.25 1.25 0 0 1 2.5 0V11" />
      <path d="M14 11V5.75a1.25 1.25 0 0 1 2.5 0V13" />
      <path d="M9 11V8.75a1.25 1.25 0 0 0-2.5 0V15a6 6 0 0 0 6 6h1a6 6 0 0 0 6-6v-2" />
    </>
  ),
  // Forward arrow to a fresh page — informational, points somewhere.
  "arrow-forward": (
    <>
      <path d="M4 6h8l4 4v8H4z" />
      <path d="M14 4h6v6" strokeWidth="1.75" />
      <path d="m13.5 10.5 6.5-6.5" strokeWidth="1.75" />
    </>
  ),
  // Cloud with a slash — our infrastructure, not the credential.
  "cloud-offline": (
    <>
      <path d="M7 18h10a4 4 0 0 0 .5-7.97 6 6 0 0 0-11.4 1.6A3.5 3.5 0 0 0 7 18Z" />
      <path d="M3.5 3.5 20.5 20.5" strokeWidth="2.25" />
    </>
  ),
  // Question mark — genuinely unknown, and indistinguishable from never-issued.
  question: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M9.6 9.4a2.5 2.5 0 0 1 4.85.85c0 1.7-2.45 2.25-2.45 3.75" strokeWidth="1.9" />
      <circle cx="12" cy="17.1" r="1.05" fill="currentColor" stroke="none" />
    </>
  ),
};

export function OutcomeGlyph({
  icon,
  className = "size-5",
}: {
  icon: OutcomeIcon;
  className?: string;
}) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      // Decorative in every use: the adjacent text always names the outcome, so
      // announcing the glyph too would read the status twice.
      aria-hidden="true"
    >
      {PATHS[icon]}
    </svg>
  );
}
