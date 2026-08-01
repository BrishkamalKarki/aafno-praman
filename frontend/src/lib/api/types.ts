/**
 * Hand-written mirrors of the serializers the consoles actually read.
 *
 * `schema.d.ts` is generated from the OpenAPI document and stays the source of
 * truth for the wire format, but several of these endpoints are declared there
 * with `DictField` / `JSONField` payloads, which generate as `unknown`. Rather
 * than cast at every call site, the handful of shapes this UI depends on are
 * written out once — and a mismatch shows up as a compile error in one file
 * instead of a runtime `undefined` in six pages.
 */

import type { RecordState } from "@/components/ui/dashboard";

/** `apps/credentials/models.py::RecordStatus` */
export type RecordStatus =
  | "DRAFT"
  | "OFFERED"
  | "DECLINED"
  | "EXPIRED"
  | "PENDING_REVIEW"
  | "REJECTED"
  | "PENDING_ANCHOR"
  | "ISSUED"
  | "REVOKED"
  | "SUPERSEDED";

export type RecordType = "ACADEMIC" | "EXPERIENCE";

export interface Anchor {
  state: "PENDING" | "CONFIRMED" | "FAILED";
  tx_hash: string;
  block_number: number | null;
  chain_id: number | null;
  contract_address: string;
  issuer_address: string;
  confirmed_at: string | null;
}

export interface AcademicDetail {
  registration_number: string;
  degree_title: string;
  major: string;
  level: string;
  graduation_date: string;
  graduation_date_bs: string;
  cgpa: string | null;
  percentage: string | null;
  honours: string;
}

export interface ExperienceDetail {
  job_title: string;
  department: string;
  employment_type: string;
  start_date: string;
  end_date: string | null;
  is_current: boolean;
  departure_status: string;
  responsibilities: string;
}

export interface CredentialRecord {
  id: string;
  record_type: RecordType;
  status: RecordStatus;
  issuance_mode: "AUTHORITY_PUSH" | "SEEKER_CLAIM";
  issuer: string;
  issuer_name: string;
  issuer_kind: "INSTITUTION" | "EMPLOYER";
  issuer_status: string;
  subject_full_name: string;
  subject_email: string;
  record_hash: string;
  document: string | null;
  document_sha256: string;
  detail: Partial<AcademicDetail & ExperienceDetail>;
  anchor: Anchor | null;
  review_note: string;
  issued_at: string | null;
  created_at: string;
}

/** `credentials/offers/` — a record plus the two fields the decision needs. */
export interface CredentialOffer extends CredentialRecord {
  title: string;
  offered_at: string | null;
  offer_expires_at: string | null;
}

export interface IssuerStats {
  total: number;
  issued: number;
  offered: number;
  declined: number;
  pending_anchor: number;
  pending_review: number;
  revoked: number;
  academic: number;
  experience: number;
}

export interface PassportResponse {
  profile: {
    full_name: string;
    headline: string;
    public_slug: string;
    passport_url: string;
    is_discoverable: boolean;
  };
  summary: {
    total: number;
    issued: number;
    pending: number;
    offered: number;
    pending_anchor: number;
    revoked: number;
    academic: number;
    experience: number;
  };
  records: CredentialRecord[];
}

export interface SeekerProfile {
  id: string;
  email: string;
  phone: string;
  legal_name: string;
  public_slug: string;
  passport_url: string;
  national_id_masked: string;
  identity_level: "EMAIL_ONLY" | "CITIZENSHIP";
  citizenship_verified_by_name: string;
  citizenship_verified_at: string | null;
  headline: string;
  date_of_birth: string | null;
  is_discoverable: boolean;
}

export interface AccessLogEntry {
  id: string;
  verifier: string;
  credential: string;
  result: string;
  created_at: string;
}

export interface ShareLink {
  id: string;
  token: string;
  url: string;
  label: string;
  include_all: boolean;
  mask_identifiers: boolean;
  expires_at: string | null;
  max_views: number | null;
  view_count: number;
  last_viewed_at: string | null;
  revoked_at: string | null;
  is_active: boolean;
  requires_passphrase: boolean;
  record_count: number;
  created_at: string;
}

export interface QuotaStatus {
  plan: "FREE" | "PRO";
  used: number;
  limit: number | null;
  remaining: number | null;
  unlimited: boolean;
  resets_at: string;
}

export interface Subscription {
  plan: "FREE" | "PRO";
  monthly_lookup_limit: number;
  started_at: string;
}

export interface VerificationLogEntry {
  id: string;
  result: string;
  record: string | null;
  subject_name: string | null;
  issuer_name: string | null;
  lookup_reference: string;
  latency_ms: number;
  counts_against_quota: boolean;
  created_at: string;
}

export interface ActivityEvent {
  id: string;
  action: string;
  label: string;
  detail: string;
  tx_hash: string;
  actor_label: string;
  object_type: string;
  object_id: string;
  created_at: string;
}

export interface Organization {
  id: string;
  kind: "INSTITUTION" | "EMPLOYER";
  legal_name: string;
  slug: string;
  registration_number: string;
  website: string;
  contact_email: string;
  contact_phone: string;
  address: string;
  status: "PENDING" | "APPROVED" | "SUSPENDED" | "REJECTED";
  status_reason: string;
  chain_address: string;
  approval_tx_hash: string;
  approved_at: string | null;
  can_issue: boolean;
  member_count: number;
  plan: string;
  created_at: string;
}

export interface RegistrarOrganization extends Organization {
  applicant: { email?: string; full_name?: string };
  issued_count: number;
}

export interface RegistrarSummary {
  pending: number;
  approved: number;
  suspended: number;
  rejected: number;
  records_issued: number;
}

export interface BatchRowError {
  row_number: number;
  raw_row: Record<string, string>;
  error: string;
}

export interface IssuanceBatch {
  id: string;
  record_type: RecordType;
  source_filename: string;
  status: "PARSING" | "COMPLETED" | "PARTIAL" | "FAILED";
  total_rows: number;
  accepted_rows: number;
  rejected_rows: number;
  anchor_tx_hash: string;
  errors: BatchRowError[];
  created_at: string;
  completed_at: string | null;
}

export interface DocumentVerifyResult {
  result: string;
  reason: string;
  document_sha256: string;
  issuer: { name?: string; kind?: string; active?: boolean } | null;
  subject_match: boolean | null;
  subject_check_available: boolean;
  identity_level: string;
  expected_hash: string;
  computed_hash: string;
  chain: Record<string, unknown>;
}

/* ------------------------------------------------------- display helpers */

/**
 * Collapse ten backend statuses onto the five pills the UI already draws.
 *
 * The mapping is not arbitrary. `PENDING_ANCHOR` shows as "Anchoring" because
 * from the holder's point of view the credential is theirs and the ledger write
 * is in progress; `EXPIRED` and `REJECTED` share the "Declined" pill because in
 * both cases nothing was published and the issuer is the one who must act.
 */
const STATUS_TO_PILL: Record<RecordStatus, RecordState> = {
  DRAFT: "PENDING",
  OFFERED: "AWAITING_CONFIRMATION",
  PENDING_REVIEW: "AWAITING_CONFIRMATION",
  PENDING_ANCHOR: "PENDING",
  ISSUED: "ACTIVE",
  DECLINED: "DECLINED",
  EXPIRED: "DECLINED",
  REJECTED: "DECLINED",
  REVOKED: "REVOKED",
  SUPERSEDED: "REVOKED",
};

export function pillFor(status: RecordStatus): RecordState {
  return STATUS_TO_PILL[status] ?? "PENDING";
}

/** The one-line name of a credential, however it is typed. */
export function recordTitle(record: CredentialRecord): string {
  if (record.record_type === "EXPERIENCE") {
    return record.detail.job_title || "Work experience";
  }
  return record.detail.degree_title || "Academic credential";
}

/**
 * Where a record stands on the ledger, in the words the UI promised to use.
 *
 * The requirement is that blockchain state is shown honestly, so an unanchored
 * record says so rather than being quietly rendered as if it were live.
 */
export function anchorLabel(record: CredentialRecord): string {
  if (record.status === "REVOKED") return "Revoked on chain";
  if (record.anchor?.state === "CONFIRMED") return "Anchored";
  if (record.status === "PENDING_ANCHOR") return "Pending anchor";
  if (record.anchor?.state === "FAILED") return "Anchor failed — will retry";
  if (record.status === "OFFERED") return "Awaiting confirmation";
  return "Not anchored";
}

/** Short form of a transaction hash or address, for tabular display. */
export function shortHash(value: string | null | undefined, lead = 10): string {
  if (!value) return "—";
  return value.length > lead + 6 ? `${value.slice(0, lead)}…${value.slice(-4)}` : value;
}

/**
 * Relative time, in the plainest possible wording.
 *
 * `Intl.RelativeTimeFormat` is used rather than a date library: it is built in,
 * it localises, and this is the only place in the app that needs it.
 */
export function timeAgo(iso: string | null | undefined): string {
  if (!iso) return "—";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "—";

  const seconds = Math.round((then - Date.now()) / 1000);
  const formatter = new Intl.RelativeTimeFormat("en", { numeric: "auto" });
  const divisions: Array<[number, Intl.RelativeTimeFormatUnit]> = [
    [60, "second"],
    [60, "minute"],
    [24, "hour"],
    [7, "day"],
    [4.35, "week"],
    [12, "month"],
  ];

  let value = seconds;
  for (const [amount, unit] of divisions) {
    if (Math.abs(value) < amount) return formatter.format(Math.round(value), unit);
    value /= amount;
  }
  return formatter.format(Math.round(value), "year");
}

/** Absolute date, for anything that belongs on a certificate. */
export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
}
