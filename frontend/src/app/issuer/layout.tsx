"use client";

import { ProtectedRoute } from "@/components/auth/protected-route";
import { WalletGate } from "@/components/auth/wallet-gate";
import { AppShell } from "@/components/shell/app-shell";
import { IssuerAccountChip } from "@/components/shell/issuer-account-chip";
import { useRecordStats } from "@/lib/api/hooks";

export default function IssuerLayout({ children }: { children: React.ReactNode }) {
  return (
    // Order matters: authenticate first, then check the operator's wallet.
    // Reversed, someone who is not signed in is asked to connect MetaMask
    // before being told they are at the wrong door.
    //
    // The wallet is an operator check, not the signer — anchoring still goes
    // out under the organisation's custodial key. See `WalletGate`.
    <ProtectedRoute allow={["ORG_MEMBER"]} requireOrgKind="INSTITUTION">
      <WalletGate>
        <IssuerShell>{children}</IssuerShell>
      </WalletGate>
    </ProtectedRoute>
  );
}

function IssuerShell({ children }: { children: React.ReactNode }) {
  const { data: stats } = useRecordStats();

  return (
    <AppShell
      surface="issuer"
      title="Issuer console"
      // Graduates who have been asked and have not answered — the number that
      // decides whether a batch is actually finished.
      badges={{ pendingOffers: stats?.offered ?? 0 }}
      account={<IssuerAccountChip />}
    >
      {children}
    </AppShell>
  );
}
