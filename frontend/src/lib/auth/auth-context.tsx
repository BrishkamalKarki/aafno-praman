"use client";

/**
 * Authentication state for the whole app.
 *
 * ## Why localStorage rather than an httpOnly cookie
 *
 * The consoles are client-rendered dashboards talking to a separate Django
 * origin, so a cookie would need `SameSite=None` plus CORS credentials plus a
 * CSRF token on every write — three moving parts to get wrong, in exchange for
 * XSS resistance the app does not otherwise have. The honest trade is stated
 * rather than hidden: a script injected into this origin can read the token.
 * The mitigation is that nothing here renders untrusted HTML, and access tokens
 * live thirty minutes.
 *
 * ## Why the token is pushed into the API client rather than imported by it
 *
 * `setTokenProvider` hands `apiFetch` a getter, so every call anywhere in the
 * app carries the current access token without importing React state. That also
 * keeps `lib/api/client.ts` usable from a server component, which importing a
 * context would not.
 *
 * ## Refresh
 *
 * Proactive, on a timer 90 seconds before expiry, and reactive, on the 401 that
 * a suspended laptop or a clock skew produces anyway. Both paths funnel into one
 * in-flight promise so a page that fires six queries at once refreshes once.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import { ApiError, apiFetch, setTokenProvider, setUnauthorizedHandler } from "@/lib/api/client";

export type Role = "SEEKER" | "ORG_MEMBER" | "REGISTRAR";
export type OrgKind = "INSTITUTION" | "EMPLOYER";

export interface OrganizationMembership {
  id: string;
  slug: string;
  name: string;
  kind: OrgKind;
  status: string;
  role: "OWNER" | "ISSUER" | "VIEWER";
  can_issue: boolean;
}

/** Mirrors `apps/accounts/serializers.py::UserSerializer`. */
export interface CurrentUser {
  id: string;
  email: string;
  full_name: string;
  phone: string;
  role: Role;
  date_joined: string;
  organizations: OrganizationMembership[];
  passport_slug: string;
}

interface TokenPair {
  access: string;
  refresh: string;
}

const STORAGE_KEY = "aafnopraman.tokens";

function readStoredTokens(): TokenPair | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<TokenPair>;
    return parsed.access && parsed.refresh
      ? { access: parsed.access, refresh: parsed.refresh }
      : null;
  } catch {
    // A corrupted entry must not brick the app on every load.
    return null;
  }
}

function writeStoredTokens(tokens: TokenPair | null): void {
  if (typeof window === "undefined") return;
  if (tokens) window.localStorage.setItem(STORAGE_KEY, JSON.stringify(tokens));
  else window.localStorage.removeItem(STORAGE_KEY);
}

/**
 * Read the `exp` claim without verifying the signature.
 *
 * Only ever used to decide *when to refresh*. Authorisation is the server's
 * job — it re-reads role and organisation status on every request, which is why
 * a token minted before an issuer was suspended grants nothing afterwards.
 */
function decodeExpiry(token: string): number | null {
  try {
    const payload = token.split(".")[1];
    if (!payload) return null;
    const json = JSON.parse(atob(payload.replace(/-/g, "+").replace(/_/g, "/"))) as {
      exp?: number;
    };
    return typeof json.exp === "number" ? json.exp * 1000 : null;
  } catch {
    return null;
  }
}

export type AuthStatus = "loading" | "authenticated" | "unauthenticated";

export interface RegisterInput {
  email: string;
  full_name: string;
  phone?: string;
  password: string;
  password_confirm: string;
}

interface AuthContextValue {
  user: CurrentUser | null;
  status: AuthStatus;
  login: (email: string, password: string) => Promise<CurrentUser>;
  register: (data: RegisterInput) => Promise<CurrentUser>;
  logout: () => void;
  reloadUser: () => Promise<CurrentUser | null>;
  /** The membership whose console the user lands in. */
  primaryOrg: OrganizationMembership | null;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<CurrentUser | null>(null);

  /**
   * Tokens live in a ref, not in state.
   *
   * Nothing renders them — `setTokenProvider` is registered once on mount and
   * has to see the newest pair on every later request, which state would give
   * it only after a re-render. Keeping them out of state also means a token
   * refresh does not repaint every console.
   *
   * Seeded lazily from storage so the first paint already knows whether there is
   * a session to restore, rather than announcing "signed out" and correcting
   * itself a tick later.
   */
  const [initialTokens] = useState<TokenPair | null>(() =>
    typeof window === "undefined" ? null : readStoredTokens(),
  );
  const tokensRef = useRef<TokenPair | null>(initialTokens);
  const [status, setStatus] = useState<AuthStatus>(
    initialTokens ? "loading" : "unauthenticated",
  );

  const refreshTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const inFlightRefresh = useRef<Promise<TokenPair | null> | null>(null);

  const clearSession = useCallback(() => {
    if (refreshTimer.current) clearTimeout(refreshTimer.current);
    refreshTimer.current = null;
    inFlightRefresh.current = null;
    tokensRef.current = null;
    setUser(null);
    writeStoredTokens(null);
    setStatus("unauthenticated");
  }, []);

  const requestRefresh = useCallback(async (): Promise<TokenPair | null> => {
    const current = tokensRef.current;
    if (!current) return null;

    // Coalesce: six parallel queries hitting 401 must not send six refreshes,
    // which with ROTATE_REFRESH_TOKENS on would invalidate each other.
    if (inFlightRefresh.current) return inFlightRefresh.current;

    inFlightRefresh.current = (async () => {
      try {
        const result = await apiFetch<{ access: string; refresh?: string }>("/auth/refresh/", {
          method: "POST",
          body: { refresh: current.refresh },
          anonymous: true,
        });
        const next: TokenPair = {
          access: result.access,
          refresh: result.refresh ?? current.refresh,
        };
        tokensRef.current = next;
        writeStoredTokens(next);
        return next;
      } catch {
        return null;
      } finally {
        inFlightRefresh.current = null;
      }
    })();

    return inFlightRefresh.current;
  }, []);

  const scheduleRefresh = useCallback(
    (accessToken: string) => {
      // `arm` is declared inside so the timer can re-arm itself without the
      // callback referring to its own binding before initialisation.
      const arm = (token: string) => {
        if (refreshTimer.current) clearTimeout(refreshTimer.current);
        const expiresAt = decodeExpiry(token);
        if (expiresAt === null) return;

        // Floor of five seconds, so an already-stale token never schedules in
        // the past and spins.
        const delay = Math.max(expiresAt - Date.now() - 90_000, 5_000);
        refreshTimer.current = setTimeout(() => {
          void requestRefresh().then((next) => {
            if (next) arm(next.access);
            else clearSession();
          });
        }, delay);
      };

      arm(accessToken);
    },
    [requestRefresh, clearSession],
  );

  useEffect(() => {
    setTokenProvider(() => tokensRef.current?.access ?? null);
    setUnauthorizedHandler(async () => (await requestRefresh())?.access ?? null);
  }, [requestRefresh]);

  const reloadUser = useCallback(async (): Promise<CurrentUser | null> => {
    try {
      const me = await apiFetch<CurrentUser>("/auth/me/");
      setUser(me);
      setStatus("authenticated");
      return me;
    } catch {
      return null;
    }
  }, []);

  // Restore a session on first paint. `tokensRef` was already seeded from
  // storage by the lazy state initialiser above, so there is nothing to set
  // synchronously here — only the network work that decides whether it is real.
  useEffect(() => {
    const stored = tokensRef.current;
    if (!stored) return;

    let cancelled = false;
    void (async () => {
      const expiresAt = decodeExpiry(stored.access);
      if (expiresAt !== null && expiresAt < Date.now()) {
        const next = await requestRefresh();
        if (!next) {
          if (!cancelled) clearSession();
          return;
        }
      }
      if (cancelled) return;

      const me = await reloadUser();
      if (cancelled) return;
      if (me) scheduleRefresh(tokensRef.current!.access);
      else clearSession();
    })();

    return () => {
      cancelled = true;
      if (refreshTimer.current) clearTimeout(refreshTimer.current);
    };
    // Mount only: this is session bootstrap, not a reaction to changing props.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const login = useCallback(
    async (email: string, password: string) => {
      const result = await apiFetch<{ access: string; refresh: string; user: CurrentUser }>(
        "/auth/login/",
        { method: "POST", body: { email, password }, anonymous: true },
      );

      const next: TokenPair = { access: result.access, refresh: result.refresh };
      tokensRef.current = next;
      writeStoredTokens(next);
      setUser(result.user);
      setStatus("authenticated");
      scheduleRefresh(next.access);
      return result.user;
    },
    [scheduleRefresh],
  );

  const register = useCallback(
    async (data: RegisterInput) => {
      // Registration returns the user but no tokens, so it is followed by a
      // login rather than reimplementing token minting on the client.
      await apiFetch<CurrentUser>("/auth/register/", {
        method: "POST",
        body: { ...data, role: "SEEKER" },
        anonymous: true,
      });
      return login(data.email, data.password);
    },
    [login],
  );

  const primaryOrg = user?.organizations?.[0] ?? null;

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      status,
      login,
      register,
      logout: clearSession,
      reloadUser,
      primaryOrg,
    }),
    [user, status, login, register, clearSession, reloadUser, primaryOrg],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside <AuthProvider>.");
  return context;
}

/** Where a signed-in user belongs. Used by login, by guards and by the 403 bounce. */
export function homeFor(role: Role, orgKind?: OrgKind): string {
  if (role === "REGISTRAR") return "/admin";
  if (role === "ORG_MEMBER") return orgKind === "EMPLOYER" ? "/employer" : "/issuer";
  return "/citizen";
}

export { ApiError };
