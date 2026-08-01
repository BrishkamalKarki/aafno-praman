/**
 * The seven verification outcomes — one source of truth for colour, icon and
 * copy.
 *
 * ## Why this is not a boolean
 *
 * The temptation in a credential product is a green tick and a red cross. It is
 * the wrong design, and the backend already refuses it (see the
 * `VerificationResult` docstring in `apps/verification/models.py`):
 *
 *   > A recruiter needs to distinguish "the data was altered" from "the
 *   > university withdrew this degree" from "our node is briefly unreachable" —
 *   > those demand three different human responses, and showing a red cross for
 *   > all of them would make the platform untrustworthy in the opposite
 *   > direction.
 *
 * A red cross on UNCONFIRMED accuses an honest graduate of forgery because an
 * RPC endpoint was restarting. That is the failure mode this table exists to
 * make impossible.
 *
 * ## Why every outcome carries an icon and a sentence
 *
 * Colour is never the only signal. Around 8% of men have some colour vision
 * deficiency, and red/green is the most common axis — precisely the two states
 * that matter most here. Each outcome therefore ships with a distinct glyph
 * shape and plain-language copy, so the meaning survives greyscale printing,
 * a monochrome screen, and colour blindness alike.
 *
 * ## Why the copy names an action
 *
 * A verifier who sees TAMPERED needs to know what to do next, not just that
 * something is wrong. `action` is what turns a status chip into a decision.
 */

export const VERIFICATION_OUTCOMES = [
  "VERIFIED",
  "TAMPERED",
  "SUBJECT_MISMATCH",
  "REVOKED",
  "SUPERSEDED",
  "UNCONFIRMED",
  "NOT_FOUND",
] as const;

export type VerificationOutcome = (typeof VERIFICATION_OUTCOMES)[number];

/** Distinct glyph shapes — never two outcomes sharing one silhouette. */
export type OutcomeIcon =
  | "check-seal"
  | "broken-doc"
  | "person-slash"
  | "hand-stop"
  | "arrow-forward"
  | "cloud-offline"
  | "question";

export interface OutcomeMeta {
  /** Short chip label. */
  label: string;
  /** One sentence stating what is factually true. */
  headline: string;
  /** What the verifier should do about it. */
  action: string;
  icon: OutcomeIcon;
  /** Token prefix — resolves to --color-{token}, -surface and -border. */
  token: string;
  /**
   * Whether this outcome means "you may rely on this credential".
   *
   * Only VERIFIED is true. SUPERSEDED is deliberately false: the record is
   * genuine but a corrected version exists, and treating it as a pass would let
   * a stale document stand in for the current one.
   */
  trustworthy: boolean;
  /**
   * Whether the outcome reflects a platform problem rather than a credential
   * problem. Drives the "this is our fault, try again" framing on UNCONFIRMED.
   */
  isPlatformFault: boolean;
}

export const OUTCOME_META: Record<VerificationOutcome, OutcomeMeta> = {
  VERIFIED: {
    label: "Verified",
    headline: "This credential is genuine and matches the ledger exactly.",
    action: "Safe to rely on. The issuer was in good standing when it was issued.",
    icon: "check-seal",
    token: "verified",
    trustworthy: true,
    isPlatformFault: false,
  },
  TAMPERED: {
    label: "Altered",
    headline: "This document does not match what the issuer committed to the ledger.",
    action:
      "Do not rely on it. The contents have been changed since issuance. Ask the candidate for the original.",
    icon: "broken-doc",
    token: "tampered",
    trustworthy: false,
    isPlatformFault: false,
  },
  SUBJECT_MISMATCH: {
    label: "Wrong person",
    headline: "This is a genuine credential, but it was not issued to the person you named.",
    action:
      "The document is real; the claim of ownership is not. Check the name and citizenship number you entered.",
    icon: "person-slash",
    token: "mismatch",
    trustworthy: false,
    isPlatformFault: false,
  },
  REVOKED: {
    label: "Revoked",
    headline: "The issuing organisation has withdrawn this credential.",
    action:
      "It was genuine when issued but is no longer valid. The issuer's stated reason is shown below.",
    icon: "hand-stop",
    token: "revoked",
    trustworthy: false,
    isPlatformFault: false,
  },
  SUPERSEDED: {
    label: "Superseded",
    headline: "A corrected version of this credential has replaced it.",
    action: "Use the current record instead — it is linked below. This copy is out of date.",
    icon: "arrow-forward",
    token: "superseded",
    trustworthy: false,
    isPlatformFault: false,
  },
  UNCONFIRMED: {
    label: "Unconfirmed",
    headline:
      "The credential's data is intact and signed by an approved issuer, but the ledger is currently unreachable.",
    action:
      "This is a problem on our side, not with the credential. Please try again shortly.",
    icon: "cloud-offline",
    token: "unconfirmed",
    trustworthy: false,
    isPlatformFault: true,
  },
  NOT_FOUND: {
    label: "Not found",
    headline: "No verified record matches this document.",
    action:
      "It may never have been issued through Aafno Praman, or the file may have been modified. Ask for the original PDF.",
    icon: "question",
    token: "notfound",
    trustworthy: false,
    isPlatformFault: false,
  },
};

/**
 * Narrow an untrusted API string to a known outcome.
 *
 * Falls back to UNCONFIRMED rather than NOT_FOUND for an unrecognised value: an
 * outcome this client does not know about means the client is out of date, and
 * "we could not confirm" is honest where "no such record" would be a false
 * accusation.
 */
export function parseOutcome(value: string | null | undefined): VerificationOutcome {
  return VERIFICATION_OUTCOMES.includes(value as VerificationOutcome)
    ? (value as VerificationOutcome)
    : "UNCONFIRMED";
}
