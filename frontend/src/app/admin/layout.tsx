"use client";

import { ProtectedRoute } from "@/components/auth/protected-route";
import { AccountChip } from "@/components/shell/account-chip";
import { AppShell } from "@/components/shell/app-shell";
import { useRegistrarSummary } from "@/lib/api/hooks";

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  return (
    <ProtectedRoute allow={["REGISTRAR"]}>
      <AdminShell>{children}</AdminShell>
    </ProtectedRoute>
  );
}

function AdminShell({ children }: { children: React.ReactNode }) {
  const { data: summary } = useRegistrarSummary();

  return (
    <AppShell
      surface="admin"
      title="Admin"
      // Applications nobody has reviewed. This is the registrar's only queue,
      // and an unreviewed application is an institution unable to issue.
      badges={{ pendingOffers: summary?.pending ?? 0 }}
      account={<AccountChip subtitle="Platform registrar" />}
    >
      {children}
    </AppShell>
  );
}
