/**
 * API client.
 *
 * Thin on purpose. Types come from `schema.d.ts`, generated straight from the
 * backend's OpenAPI document, so frontend/backend drift is a compile error
 * rather than a runtime surprise. Regenerate with `npm run api:types`.
 *
 * The only real logic here is error normalisation: the Django side returns one
 * envelope for every non-2xx response, and unwrapping it in one place means
 * components branch on a stable `code` instead of string-matching messages.
 */

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000/api/v1";

/** Matches `apps/common/exceptions.py::api_exception_handler`. */
export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
    details?: Record<string, unknown>;
    retry_after_seconds?: number;
  };
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: Record<string, unknown>;
  readonly retryAfterSeconds: number | undefined;

  constructor(status: number, body: Partial<ApiErrorBody>) {
    const error = body.error;
    super(error?.message ?? "Something went wrong.");
    this.name = "ApiError";
    this.status = status;
    this.code = error?.code ?? "error";
    this.details = error?.details ?? {};
    this.retryAfterSeconds = error?.retry_after_seconds;
  }

  /** Quota exhausted — the employer paywall, not a failure. */
  get isQuotaExceeded(): boolean {
    return this.code === "quota_exceeded";
  }

  /** The org has applied but the registrar has not approved it yet. */
  get isIssuerNotApproved(): boolean {
    return this.code === "issuer_not_approved";
  }
}

type Token = string | null;

/**
 * Access-token accessor, injected rather than imported.
 *
 * Keeps this module free of React and of any particular storage choice, so the
 * same client works in a server component, a route handler and the browser.
 */
let getAccessToken: () => Token = () => null;

export function setTokenProvider(provider: () => Token): void {
  getAccessToken = provider;
}

/**
 * Refresh hook, injected for the same reason as the token getter.
 *
 * Returns a fresh access token, or null when the session is genuinely over. The
 * proactive timer in the auth context handles the ordinary case; this covers the
 * ones a timer cannot — a laptop resumed from sleep, a skewed clock, a token
 * invalidated server-side. Exactly one retry per request: a refresh that keeps
 * yielding 401 is a dead session, and looping on it would turn a logout into a
 * request storm.
 */
let onUnauthorized: (() => Promise<Token>) | null = null;

export function setUnauthorizedHandler(handler: (() => Promise<Token>) | null): void {
  onUnauthorized = handler;
}

export interface RequestOptions {
  method?: "GET" | "POST" | "PATCH" | "PUT" | "DELETE";
  body?: unknown;
  /** Sent as multipart. Used by document upload and certificate attachment. */
  formData?: FormData;
  signal?: AbortSignal;
  /** Skip the Authorization header — public endpoints, e.g. confirmation links. */
  anonymous?: boolean;
}

export async function apiFetch<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, formData, signal, anonymous = false } = options;

  // FormData sets its own multipart boundary; never stringify it and never
  // declare a content type for it.
  const requestBody = formData ?? (body === undefined ? null : JSON.stringify(body));

  const send = async (token: Token): Promise<Response> => {
    const headers: Record<string, string> = {};
    if (!formData && body !== undefined) headers["Content-Type"] = "application/json";
    if (token) headers["Authorization"] = `Bearer ${token}`;

    // Optional members are spread in rather than set to `undefined`. Under
    // `exactOptionalPropertyTypes` an explicit `undefined` is not the same as an
    // absent key, and `RequestInit` accepts absence but not undefined.
    return fetch(`${BASE_URL}${path}`, {
      method,
      headers,
      ...(requestBody === null ? {} : { body: requestBody }),
      ...(signal ? { signal } : {}),
    });
  };

  let response = await send(anonymous ? null : getAccessToken());

  if (response.status === 401 && !anonymous && onUnauthorized) {
    const refreshed = await onUnauthorized();
    // Only retry when a genuinely new token came back. Replaying the request
    // with the same expired one just burns another round trip.
    if (refreshed) response = await send(refreshed);
  }

  if (response.status === 204) return undefined as T;

  const text = await response.text();
  const payload = text ? safeParse(text) : {};

  if (!response.ok) {
    throw new ApiError(response.status, payload as Partial<ApiErrorBody>);
  }
  return payload as T;
}

/**
 * Same auth handling, binary response.
 *
 * Used by the QR endpoint, which returns a PNG. An `<img src>` cannot carry an
 * Authorization header, so the bytes are fetched here and handed to the DOM as
 * an object URL instead.
 */
export async function apiFetchBlob(path: string): Promise<Blob> {
  const send = (token: Token) =>
    fetch(`${BASE_URL}${path}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });

  let response = await send(getAccessToken());
  if (response.status === 401 && onUnauthorized) {
    const refreshed = await onUnauthorized();
    if (refreshed) response = await send(refreshed);
  }

  if (!response.ok) {
    const text = await response.text();
    throw new ApiError(response.status, (text ? safeParse(text) : {}) as Partial<ApiErrorBody>);
  }
  return response.blob();
}

function safeParse(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    // A non-JSON body from an API that always returns JSON means something
    // upstream failed — a proxy error page, most often. Surfacing the raw text
    // is more useful than a parse exception.
    return { error: { code: "invalid_response", message: text.slice(0, 200) } };
  }
}
