/**
 * The Aafno Praman mark and wordmark.
 *
 * ## Why the mark is drawn rather than imported
 *
 * The supplied artwork is a raster PNG on an opaque white card. Dropping that
 * into the sidebar would put a white rectangle on a near-black surface in dark
 * mode, and it would go soft on any display above 1x. Redrawing it as geometry
 * costs about forty lines and makes the mark resolution-independent, themeable,
 * and 1.5 kB instead of 90 kB.
 *
 * ## Why it inherits `currentColor`
 *
 * The brand navy (#1b2a4a) is very close to the dark-theme canvas (#0b1120) —
 * roughly a 1.3:1 contrast ratio, which is invisible in practice. So the mark
 * takes its colour from whatever it is placed on rather than hard-coding the
 * navy, and the navy is reserved for light surfaces and the favicon, where it
 * is what the artwork actually specifies.
 *
 * The three parts — mortarboard, shield, seal — are the three claims the
 * product makes, which is why the drawing keeps them separable: the credential
 * is academic, it is protected, it has been checked.
 */

export function LogoMark({
  size = 28,
  className,
  title,
}: {
  size?: number;
  className?: string;
  /** Supply only when the mark stands alone; otherwise the wordmark names it. */
  title?: string;
}) {
  return (
    <svg
      viewBox="0 0 44 50"
      width={size}
      height={size * (50 / 44)}
      className={className}
      fill="none"
      stroke="currentColor"
      strokeWidth={3.4}
      strokeLinecap="round"
      strokeLinejoin="round"
      role={title ? "img" : "presentation"}
      aria-hidden={title ? undefined : true}
      focusable="false"
    >
      {title && <title>{title}</title>}

      {/* Shield — the outline everything else sits inside. */}
      <path d="M4 11 22 4.4 40 11v14.6c0 9.4-7.4 16.6-18 19.8C11.4 42.2 4 35 4 25.6Z" />

      {/* Mortarboard — the shield's crown, filled so it reads as a cap and not
          as a second outline competing with the shield's own edge. Its stroke
          is thinner than the shield's; at the same weight the band swallowed
          the shield's top corners and the cap stopped being legible as one. */}
      <path d="M5 11 22 4.9 39 11v2.6L22 17.4 5 13.6Z" fill="currentColor" strokeWidth={1.4} />

      {/* Seal — deliberately open at the upper right so the tick breaks out of
          it. A closed ring with a tick inside reads as a checkbox; a tick
          escaping the ring reads as a mark being granted. The arc endpoints are
          load-bearing: put the gap at 3 o'clock instead and the tick crosses
          the ring's stroke rather than passing through it. */}
      <path d="M24.4 23.4A8.6 8.6 0 1 0 29.6 34.4" strokeWidth={3} />
      <path d="M16.3 31.8 20.6 36.1 32.5 22.8" strokeWidth={3} />
    </svg>
  );
}

/**
 * Mark plus wordmark, as it appears in the sidebar and on every public page.
 *
 * `PRAMAN` is weighted the same as `AAFNO` — the artwork sets both in a single
 * bold weight, and the split-weight treatment used for the previous name would
 * misrepresent it.
 */
export function Logo({
  size = 28,
  className,
  showWordmark = true,
}: {
  size?: number;
  className?: string;
  showWordmark?: boolean;
}) {
  return (
    <span className={className} style={{ display: "inline-flex", alignItems: "center", gap: "0.5rem" }}>
      <LogoMark size={size} {...(showWordmark ? {} : { title: "Aafno Praman" })} />
      {showWordmark && (
        <span className="font-semibold tracking-tight whitespace-nowrap">Aafno Praman</span>
      )}
    </span>
  );
}
