"use client";

import { useState } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { ApiError } from "@/lib/api/client";
import { AuthProvider } from "@/lib/auth/auth-context";
import { ToastProvider } from "@/lib/toast";
import { WalletProvider } from "@/lib/wallet/wallet-context";

/**
 * Everything the consoles need in one client boundary.
 *
 * Order matters: `AuthProvider` registers the token getter that `apiFetch` uses,
 * so it wraps the query client rather than sitting inside it.
 */
export function Providers({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            /**
             * Never retry a 4xx. A 403 from a suspended issuer or a 400 from a
             * bad filter will return exactly the same answer three times, and
             * the delay only makes the error look like a hang.
             */
            retry: (failureCount, error) =>
              error instanceof ApiError && error.status < 500 ? false : failureCount < 2,
            staleTime: 15_000,
            // The dashboards are read-mostly and every tab switch refetching
            // both burns an employer's quota view and makes the page flicker.
            refetchOnWindowFocus: false,
          },
          mutations: { retry: false },
        },
      }),
  );

  return (
    <AuthProvider>
      <QueryClientProvider client={queryClient}>
        {/* Wallet state is global rather than mounted inside the two consoles
            that gate on it, so switching accounts in MetaMask is observed once
            instead of per-console — and so the account chip can read it. */}
        <WalletProvider>
          <ToastProvider>{children}</ToastProvider>
        </WalletProvider>
      </QueryClientProvider>
    </AuthProvider>
  );
}
