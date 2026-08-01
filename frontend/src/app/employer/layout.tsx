"use client";

import { ProtectedRoute } from "@/components/auth/protected-route";
import { WalletGate } from "@/components/auth/wallet-gate";
import { AccountChip } from "@/components/shell/account-chip";
import { AppShell } from "@/components/shell/app-shell";
import { useClaims, useMyOrganization } from "@/lib/api/hooks";

export default function EmployerLayout({ children }: { children: React.ReactNode }) {
  return (
    // Same pairing as the issuer console: sign in, then confirm the operator.
    // An employer console can confirm employment claims, which anchor under the
    // company's name — a write to the ledger, so it sits behind the gate too.
    <ProtectedRoute allow={["ORG_MEMBER"]} requireOrgKind="EMPLOYER">
      <WalletGate>
        <EmployerShell>{children}</EmployerShell>
      </WalletGate>
    </ProtectedRoute>
  );
}

function EmployerShell({ children }: { children: React.ReactNode }) {
  const { data: organization } = useMyOrganization();
  const { data: claims } = useClaims();

  return (
    <AppShell
      surface="employer"
      title="Employer console"
      // Ex-employees waiting on this company to confirm their history. It is the
      // company's own queue, so it belongs in the nav badge next to the citizen
      // equivalent rather than being discovered by opening the page.
      badges={{ pendingOffers: claims?.length ?? 0 }}
      account={<AccountChip {...(organization ? { subtitle: organization.legal_name } : {})} />}
    >
      {children}
    </AppShell>
  );
}
