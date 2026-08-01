"use client";

import { Logo } from "@/components/brand/logo";
import { RouteSpinner } from "@/components/auth/protected-route";
import { Button } from "@/components/ui/button";
import { Card, CardBody } from "@/components/ui/card";
import { FormError } from "@/components/ui/form";
import { Icon } from "@/components/ui/icon";
import { useAuth } from "@/lib/auth/auth-context";
import { CHAIN_NAME } from "@/lib/chain";
import { useWallet } from "@/lib/wallet/wallet-context";

/**
 * Requires a connected wallet on the right network before an organisation
 * console opens.
 *
 * Wraps the institution and employer consoles only — the two that can write to
 * the ledger. Citizens and the registrar never see it: making a graduate
 * install a browser extension to accept their own degree would exclude most of
 * the people this platform exists for.
 *
 * ## The copy is careful about one thing
 *
 * Staff will reasonably assume that connecting a wallet means the wallet signs
 * their credentials. It does not — signing is custodial and server-side. Every
 * screen below says so, because someone who believes their MetaMask account is
 * what makes a degree valid will draw exactly the wrong conclusion when they
 * later switch accounts and nothing changes.
 */
export function WalletGate({ children }: { children: React.ReactNode }) {
  const { status, address, connect, switchNetwork, connecting, error, disconnect } = useWallet();
  const { logout } = useAuth();

  if (status === "detecting") return <RouteSpinner />;
  if (status === "connected") return <>{children}</>;

  return (
    <main
      id="main"
      className="mx-auto flex min-h-dvh w-full max-w-md flex-col justify-center px-5 py-16"
    >
      <Logo className="text-sm text-brand" size={22} />
      <h1 className="mt-2 text-2xl font-semibold tracking-tight">
        {status === "wrong-network" ? `Switch to ${CHAIN_NAME}` : "Connect your wallet"}
      </h1>
      <p className="mt-1.5 text-sm text-text-muted">
        {status === "unavailable"
          ? "Institution and employer consoles require MetaMask on this device."
          : status === "wrong-network"
            ? `Your wallet is connected to a different network. This organisation publishes credentials to ${CHAIN_NAME}.`
            : "Institution and employer accounts confirm the person at the keyboard before the console opens."}
      </p>

      <Card raised className="mt-6">
        <CardBody className="space-y-4 pt-5">
          <FormError message={error} />

          {status === "unavailable" ? (
            <>
              <p className="text-sm text-text-muted">
                MetaMask is a browser extension that holds an account on {CHAIN_NAME}. Install it,
                then reload this page.
              </p>
              {/* An anchor, not a Button — `Button` renders a <button>, and a
                  navigation styled as one loses middle-click, "open in new
                  tab", and the status-bar preview of where it goes. */}
              <a
                href="https://metamask.io/download/"
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex h-12 w-full items-center justify-center gap-2 rounded-[var(--radius-control)] bg-brand px-6 text-base font-medium text-white transition-colors hover:bg-brand-hover"
              >
                Get MetaMask
              </a>
            </>
          ) : status === "wrong-network" ? (
            <Button size="lg" className="w-full" onClick={() => void switchNetwork()}>
              Switch to {CHAIN_NAME}
            </Button>
          ) : (
            <Button
              size="lg"
              className="w-full"
              loading={connecting}
              onClick={() => void connect()}
            >
              <Icon name="wallet" size={17} />
              Connect MetaMask
            </Button>
          )}

          {/* The single most important sentence on this screen. Without it,
              staff conclude the wallet is what signs their degrees, and act on
              that belief the first time they change accounts. */}
          <p className="border-t border-border pt-4 text-xs leading-relaxed text-text-subtle">
            This confirms who is operating the console. It does not sign anything: credentials are
            signed with your organisation&apos;s key, which the platform generates and holds. You
            will never be asked to approve a transaction or to pay gas.
          </p>
        </CardBody>
      </Card>

      {address && (
        <p className="mt-4 text-center text-xs text-text-subtle">
          Connected as <span className="font-mono">{address.slice(0, 6)}…{address.slice(-4)}</span>
          {" · "}
          <button type="button" onClick={disconnect} className="underline hover:text-text">
            use a different account
          </button>
        </p>
      )}

      <p className="mt-4 text-center text-sm">
        <button type="button" onClick={logout} className="text-text-subtle hover:text-text">
          Sign out
        </button>
      </p>
    </main>
  );
}
