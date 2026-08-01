"use client";

import { ProtectedRoute } from "@/components/auth/protected-route";
import { AccountChip } from "@/components/shell/account-chip";
import { AppShell } from "@/components/shell/app-shell";
import { useOffers } from "@/lib/api/hooks";

export default function CitizenLayout({ children }: { children: React.ReactNode }) {
  return (
    <ProtectedRoute allow={["SEEKER"]}>
      <CitizenShell>{children}</CitizenShell>
    </ProtectedRoute>
  );
}

/**
 * Split from the guard so the offer count is fetched only once the session is
 * known good. Called above `ProtectedRoute`, a signed-out visitor would fire a
 * 401 on their way to being redirected.
 */
function CitizenShell({ children }: { children: React.ReactNode }) {
  const { data: offers } = useOffers();

  return (
    <AppShell
      surface="citizen"
      title="My credentials"
      badges={{ pendingOffers: offers?.length ?? 0 }}
      account={<AccountChip />}
    >
      {children}
    </AppShell>
  );
}
