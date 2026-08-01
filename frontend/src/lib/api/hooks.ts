"use client";

/**
 * Every server read and write the consoles make, in one place.
 *
 * Colocating them is what makes the cache invalidation legible: accepting a
 * credential offer has to refresh the offer inbox, the passport and the access
 * log, and that fact belongs next to the mutation rather than scattered across
 * the three pages that happen to display those things.
 *
 * Query keys are arrays whose first element names the resource, so a mutation
 * can invalidate a whole family with one prefix.
 */

import { useCallback, useState } from "react";
import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
  type UseQueryResult,
} from "@tanstack/react-query";

import { apiFetch, apiFetchBlob } from "@/lib/api/client";
import { listOf, type Paginated } from "@/lib/api/errors";
import type {
  AccessLogEntry,
  ActivityEvent,
  CredentialOffer,
  CredentialRecord,
  DocumentVerifyResult,
  IssuanceBatch,
  IssuerStats,
  Organization,
  PassportResponse,
  QuotaStatus,
  RegistrarOrganization,
  RegistrarSummary,
  SeekerProfile,
  ShareLink,
  Subscription,
  VerificationLogEntry,
} from "@/lib/api/types";

export const keys = {
  passport: ["passport"] as const,
  offers: ["offers"] as const,
  accessLog: ["access-log"] as const,
  shareLinks: ["share-links"] as const,
  seekerProfile: ["seeker-profile"] as const,
  records: ["records"] as const,
  recordStats: ["records", "stats"] as const,
  claims: ["claims"] as const,
  batches: ["batches"] as const,
  organization: ["organization"] as const,
  activity: ["activity"] as const,
  subscription: ["subscription"] as const,
  quota: ["quota"] as const,
  verifyHistory: ["verify-history"] as const,
  registrarOrgs: ["registrar", "organizations"] as const,
  registrarSummary: ["registrar", "summary"] as const,
};

/* ------------------------------------------------------------- citizen */

export function usePassport(): UseQueryResult<PassportResponse> {
  return useQuery({
    queryKey: keys.passport,
    queryFn: () => apiFetch<PassportResponse>("/passport/"),
  });
}

export function useOffers(): UseQueryResult<CredentialOffer[]> {
  return useQuery({
    queryKey: keys.offers,
    queryFn: async () =>
      listOf(await apiFetch<Paginated<CredentialOffer>>("/credentials/offers/")),
  });
}

export function useAccessLog(): UseQueryResult<AccessLogEntry[]> {
  return useQuery({
    queryKey: keys.accessLog,
    queryFn: async () =>
      listOf(await apiFetch<Paginated<AccessLogEntry>>("/passport/access-log/")),
  });
}

export function useShareLinks(): UseQueryResult<ShareLink[]> {
  return useQuery({
    queryKey: keys.shareLinks,
    queryFn: async () => listOf(await apiFetch<Paginated<ShareLink>>("/passport/share-links/")),
  });
}

export function useSeekerProfile(): UseQueryResult<SeekerProfile> {
  return useQuery({
    queryKey: keys.seekerProfile,
    queryFn: () => apiFetch<SeekerProfile>("/auth/me/seeker-profile/"),
  });
}

/**
 * Answer a credential offer.
 *
 * Accepting queues an on-chain anchor, so the passport is invalidated too — the
 * record moves out of "waiting for you" and into the holder's credential list in
 * the same instant, and a stale list would show it in both places.
 */
export function useAnswerOffer(): UseMutationResult<
  unknown,
  Error,
  { id: string; action: "accept" | "decline"; reason?: string }
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, action, reason }) =>
      apiFetch(`/credentials/offers/${id}/${action}/`, {
        method: "POST",
        ...(action === "decline" ? { body: { reason: reason ?? "" } } : {}),
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: keys.offers });
      void queryClient.invalidateQueries({ queryKey: keys.passport });
    },
  });
}

export interface ShareLinkInput {
  label: string;
  include_all: boolean;
  mask_identifiers: boolean;
  record_ids?: string[];
  expires_at?: string | null;
  passphrase?: string;
  max_views?: number | null;
}

export function useCreateShareLink(): UseMutationResult<ShareLink, Error, ShareLinkInput> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body) =>
      apiFetch<ShareLink>("/passport/share-links/", { method: "POST", body }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: keys.shareLinks }),
  });
}

export function useRevokeShareLink(): UseMutationResult<unknown, Error, string> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id) => apiFetch(`/passport/share-links/${id}/`, { method: "DELETE" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: keys.shareLinks }),
  });
}

/**
 * Fetch a share link's QR code as an object URL.
 *
 * Outside `apiFetch` because the response is a PNG, not JSON — and outside an
 * `<img src>` because the endpoint is authenticated and an image request
 * carries no Authorization header.
 */
export function useMyShareLinkQr(): {
  fetchQr: (id: string) => Promise<string>;
  isPending: boolean;
} {
  const [isPending, setPending] = useState(false);

  const fetchQr = useCallback(async (id: string) => {
    setPending(true);
    try {
      const blob = await apiFetchBlob(`/passport/share-links/${id}/qr/`);
      return URL.createObjectURL(blob);
    } finally {
      setPending(false);
    }
  }, []);

  return { fetchQr, isPending };
}

/**
 * Log past employment for an employer to endorse.
 *
 * The other direction of issuance, and the half that was missing: the employer
 * console has a claims inbox, but until this existed nothing in the product
 * could put anything in it.
 *
 * The employer is chosen from approved organisations by id rather than typed as
 * free text — a candidate who could "claim" a job at a company with no account
 * here would be asserting something nobody can dispute, which is the exact
 * fraud the platform exists to stop.
 */
export function useClaimExperience(): UseMutationResult<
  CredentialRecord,
  Error,
  { employer: string; detail: Record<string, string | boolean> }
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body) =>
      apiFetch<CredentialRecord>("/credentials/claim-experience/", { method: "POST", body }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: keys.passport }),
  });
}

export interface DirectoryOrganization {
  id: string;
  legal_name: string;
  kind: "INSTITUTION" | "EMPLOYER";
  slug: string;
}

/** Approved organisations, by name — the picker behind a seeker claim. */
export function useOrganizationDirectory(
  kind?: "INSTITUTION" | "EMPLOYER",
): UseQueryResult<DirectoryOrganization[]> {
  const suffix = kind ? `?kind=${kind}` : "";
  return useQuery({
    queryKey: ["org-directory", suffix],
    queryFn: async () =>
      listOf(await apiFetch<Paginated<DirectoryOrganization>>(`/organizations/directory/${suffix}`)),
  });
}

export function useChangePassword(): UseMutationResult<
  { detail: string },
  Error,
  { current_password: string; new_password: string }
> {
  return useMutation({
    mutationFn: (body) =>
      apiFetch<{ detail: string }>("/auth/me/password/", { method: "POST", body }),
  });
}

export interface Candidate {
  id: string;
  full_name: string;
  headline: string;
  public_slug: string;
  verified_academic_count: number;
  verified_experience_count: number;
  highest_qualification: string;
}

export function useCandidates(search: string): UseQueryResult<Candidate[]> {
  const suffix = search.trim() ? `?q=${encodeURIComponent(search.trim())}` : "";
  return useQuery({
    queryKey: ["candidates", suffix],
    queryFn: async () => listOf(await apiFetch<Paginated<Candidate>>(`/verify/candidates/${suffix}`)),
  });
}

export interface OrganizationMember {
  id: string;
  email: string;
  full_name: string;
  role: "OWNER" | "ISSUER" | "VIEWER";
  created_at: string;
}

export function useOrganizationMembers(): UseQueryResult<OrganizationMember[]> {
  return useQuery({
    queryKey: ["org-members"],
    queryFn: async () =>
      listOf(await apiFetch<Paginated<OrganizationMember>>("/organizations/me/members/")),
  });
}

export interface OrganizationDocument {
  id: string;
  doc_type: string;
  file: string;
  sha256: string;
  created_at: string;
}

export function useOrganizationDocuments(): UseQueryResult<OrganizationDocument[]> {
  return useQuery({
    queryKey: ["org-documents"],
    queryFn: async () =>
      listOf(await apiFetch<Paginated<OrganizationDocument>>("/organizations/me/documents/")),
  });
}

export function useUploadOrganizationDocument(): UseMutationResult<
  OrganizationDocument,
  Error,
  { file: File; doc_type: string }
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ file, doc_type }) => {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("doc_type", doc_type);
      return apiFetch<OrganizationDocument>("/organizations/me/documents/", {
        method: "POST",
        formData,
      });
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["org-documents"] }),
  });
}

export function useUpdateSeekerProfile(): UseMutationResult<
  SeekerProfile,
  Error,
  Partial<Pick<SeekerProfile, "headline" | "is_discoverable">>
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body) =>
      apiFetch<SeekerProfile>("/auth/me/seeker-profile/", { method: "PATCH", body }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: keys.seekerProfile });
      void queryClient.invalidateQueries({ queryKey: keys.passport });
    },
  });
}

/* -------------------------------------------------------------- issuer */

export function useRecordStats(): UseQueryResult<IssuerStats> {
  return useQuery({
    queryKey: keys.recordStats,
    queryFn: () => apiFetch<IssuerStats>("/credentials/records/stats/"),
  });
}

export function useRecords(params?: {
  search?: string;
  status?: string;
  record_type?: string;
}): UseQueryResult<CredentialRecord[]> {
  const query = new URLSearchParams();
  if (params?.search) query.set("search", params.search);
  if (params?.status) query.set("status", params.status);
  if (params?.record_type) query.set("record_type", params.record_type);
  const suffix = query.toString() ? `?${query}` : "";

  return useQuery({
    queryKey: [...keys.records, suffix],
    queryFn: async () =>
      listOf(await apiFetch<Paginated<CredentialRecord>>(`/credentials/records/${suffix}`)),
  });
}

export function useActivity(): UseQueryResult<ActivityEvent[]> {
  return useQuery({
    queryKey: keys.activity,
    queryFn: async () =>
      listOf(await apiFetch<Paginated<ActivityEvent>>("/organizations/me/activity/")),
  });
}

export function useMyOrganization(enabled = true): UseQueryResult<Organization> {
  return useQuery({
    queryKey: keys.organization,
    queryFn: () => apiFetch<Organization>("/organizations/me/"),
    enabled,
  });
}

export function useRevokeRecord(): UseMutationResult<
  CredentialRecord,
  Error,
  { id: string; reason: string }
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, reason }) =>
      apiFetch<CredentialRecord>(`/credentials/records/${id}/revoke/`, {
        method: "POST",
        body: { reason },
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: keys.records });
      void queryClient.invalidateQueries({ queryKey: keys.recordStats });
      void queryClient.invalidateQueries({ queryKey: keys.activity });
    },
  });
}

/**
 * Issue one credential.
 *
 * Multipart rather than JSON, because the certificate file is optional but
 * common, and one code path is easier to trust than two. Nested detail fields
 * are flattened to `detail.<field>`, which is how DRF's `MultiPartParser`
 * reassembles a nested serializer.
 */
export function useIssueRecord(
  kind: "academic" | "experience",
): UseMutationResult<CredentialRecord, Error, IssueInput> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ subject_full_name, subject_email, national_id, detail, document }) => {
      const formData = new FormData();
      formData.append("subject_full_name", subject_full_name);
      formData.append("subject_email", subject_email);
      if (national_id) formData.append("national_id", national_id);
      for (const [field, value] of Object.entries(detail)) {
        if (value === undefined || value === null || value === "") continue;
        formData.append(`detail.${field}`, String(value));
      }
      if (document) formData.append("document", document);

      return apiFetch<CredentialRecord>(`/credentials/issue/${kind}/`, {
        method: "POST",
        formData,
      });
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: keys.records });
      void queryClient.invalidateQueries({ queryKey: keys.recordStats });
      void queryClient.invalidateQueries({ queryKey: keys.activity });
    },
  });
}

export interface IssueInput {
  subject_full_name: string;
  subject_email: string;
  national_id?: string;
  detail: Record<string, string | number | boolean | null | undefined>;
  document?: File | null;
}

export function useUploadBatch(): UseMutationResult<
  IssuanceBatch,
  Error,
  { file: File; record_type: "ACADEMIC" | "EXPERIENCE" }
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ file, record_type }) => {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("record_type", record_type);
      return apiFetch<IssuanceBatch>("/credentials/batches/upload/", {
        method: "POST",
        formData,
      });
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: keys.records });
      void queryClient.invalidateQueries({ queryKey: keys.recordStats });
      void queryClient.invalidateQueries({ queryKey: keys.batches });
      void queryClient.invalidateQueries({ queryKey: keys.activity });
    },
  });
}

/* ------------------------------------------------------------ employer */

export function useQuota(): UseQueryResult<QuotaStatus> {
  return useQuery({
    queryKey: keys.quota,
    queryFn: () => apiFetch<QuotaStatus>("/verify/quota/"),
  });
}

export function useSubscription(): UseQueryResult<Subscription> {
  return useQuery({
    queryKey: keys.subscription,
    queryFn: () => apiFetch<Subscription>("/organizations/me/subscription/"),
  });
}

export function useChangePlan(): UseMutationResult<Subscription, Error, "FREE" | "PRO"> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (plan) =>
      apiFetch<Subscription>("/organizations/me/subscription/", {
        method: "PATCH",
        body: { plan },
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: keys.subscription });
      // The quota limit moves with the plan, so a stale meter would show the
      // old allowance next to the new plan name.
      void queryClient.invalidateQueries({ queryKey: keys.quota });
    },
  });
}

export function useVerificationHistory(result?: string): UseQueryResult<VerificationLogEntry[]> {
  const suffix = result ? `?result=${encodeURIComponent(result)}` : "";
  return useQuery({
    queryKey: [...keys.verifyHistory, suffix],
    queryFn: async () =>
      listOf(await apiFetch<Paginated<VerificationLogEntry>>(`/verify/history/${suffix}`)),
  });
}

export function useVerifyDocument(): UseMutationResult<
  DocumentVerifyResult,
  Error,
  { document: File; claimed_name?: string; claimed_national_id?: string }
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ document, claimed_name, claimed_national_id }) => {
      const formData = new FormData();
      formData.append("document", document);
      if (claimed_name?.trim()) formData.append("claimed_name", claimed_name.trim());
      if (claimed_national_id?.trim()) {
        formData.append("claimed_national_id", claimed_national_id.trim());
      }
      return apiFetch<DocumentVerifyResult>("/verify/document/", { method: "POST", formData });
    },
    onSuccess: () => {
      // A metered lookup has just been spent; the meter must not lag behind it.
      void queryClient.invalidateQueries({ queryKey: keys.quota });
      void queryClient.invalidateQueries({ queryKey: keys.verifyHistory });
    },
  });
}

export function useClaims(): UseQueryResult<CredentialRecord[]> {
  return useQuery({
    queryKey: keys.claims,
    queryFn: async () =>
      listOf(await apiFetch<Paginated<CredentialRecord>>("/credentials/claims/")),
  });
}

export function useReviewClaim(): UseMutationResult<
  CredentialRecord,
  Error,
  { id: string; action: "endorse" | "reject"; note: string }
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, action, note }) =>
      apiFetch<CredentialRecord>(`/credentials/claims/${id}/${action}/`, {
        method: "POST",
        body: { note },
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: keys.claims });
      void queryClient.invalidateQueries({ queryKey: keys.records });
      void queryClient.invalidateQueries({ queryKey: keys.recordStats });
      void queryClient.invalidateQueries({ queryKey: keys.activity });
    },
  });
}

/* ------------------------------------------------------------ registrar */

export function useRegistrarSummary(): UseQueryResult<RegistrarSummary> {
  return useQuery({
    queryKey: keys.registrarSummary,
    queryFn: () => apiFetch<RegistrarSummary>("/registrar/organizations/summary/"),
  });
}

export function useRegistrarOrganizations(status?: string): UseQueryResult<
  RegistrarOrganization[]
> {
  const suffix = status ? `?status=${encodeURIComponent(status)}` : "";
  return useQuery({
    queryKey: [...keys.registrarOrgs, suffix],
    queryFn: async () =>
      listOf(
        await apiFetch<Paginated<RegistrarOrganization>>(`/registrar/organizations/${suffix}`),
      ),
  });
}

export function useOrganizationTransition(): UseMutationResult<
  RegistrarOrganization,
  Error,
  { id: string; action: "approve" | "reject" | "suspend" | "reinstate"; reason?: string }
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, action, reason }) =>
      apiFetch<RegistrarOrganization>(`/registrar/organizations/${id}/${action}/`, {
        method: "POST",
        // approve and reinstate take no body; reject and suspend require a
        // reason, which the backend makes mandatory so a suspended issuer is
        // never left guessing what to fix.
        ...(action === "reject" || action === "suspend" ? { body: { reason } } : {}),
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: keys.registrarOrgs });
      void queryClient.invalidateQueries({ queryKey: keys.registrarSummary });
    },
  });
}

export interface ProvisionSeekerInput {
  full_name: string;
  email: string;
  phone?: string;
  date_of_birth?: string;
  address?: string;
}

export interface ProvisionOrganizationInput {
  kind: "INSTITUTION" | "EMPLOYER";
  legal_name: string;
  email: string;
  registration_number: string;
  contact_person?: string;
  phone?: string;
  address?: string;
  website?: string;
}

export interface ProvisionResult {
  user: { email: string; full_name: string; role: string };
  organization?: Organization;
  temp_password: string;
}

export function useProvisionAccount(
  target: "user" | "organization",
): UseMutationResult<ProvisionResult, Error, ProvisionSeekerInput | ProvisionOrganizationInput> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body) =>
      apiFetch<ProvisionResult>(`/registrar/provision/${target}/`, { method: "POST", body }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: keys.registrarOrgs });
      void queryClient.invalidateQueries({ queryKey: keys.registrarSummary });
    },
  });
}

/* --------------------------------------------------------------- ledger */

export interface LedgerStatus {
  ledger: {
    ok: boolean;
    enabled: boolean;
    chain_id?: number;
    block_number?: number;
    contract_address?: string;
    error?: string;
  };
  local: { confirmed_anchors: number; pending_anchors: number; failed_anchors: number };
}

export function useLedgerStatus(): UseQueryResult<LedgerStatus> {
  return useQuery({
    queryKey: ["ledger-status"],
    queryFn: () => apiFetch<LedgerStatus>("/ledger/status/"),
    // The node going down is the one thing on these screens that changes
    // without anybody clicking, so this is the single polled query in the app.
    refetchInterval: 30_000,
  });
}
