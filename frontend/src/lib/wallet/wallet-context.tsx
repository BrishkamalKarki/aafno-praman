"use client";

/**
 * MetaMask connection state for the organisation consoles.
 *
 * ## What this wallet does and does not do
 *
 * It does **not** sign credentials. Anchoring is signed server-side with the
 * organisation's custodial key (`apps/organizations/keys.py`), generated when
 * the registrar approves it, and that is deliberate: a university registrar
 * cannot be asked to hold a seed phrase that, if lost, permanently ends their
 * ability to issue degrees.
 *
 * What connecting establishes is that the person operating the console holds a
 * key on the network their organisation publishes to — a second factor bound to
 * hardware rather than to an emailed password, on the two consoles that can
 * write to the ledger. The citizen and registrar consoles are deliberately
 * outside it: a graduate accepting their own degree must never need a browser
 * extension.
 *
 * The gate is therefore an operator check, not a signing step, and the UI says
 * so rather than implying the wallet is what makes a credential valid.
 *
 * ## Why this is not a security boundary
 *
 * Like `ProtectedRoute`, this runs in the browser and anyone can bypass it with
 * devtools. Authorisation is DRF's, re-read from the database on every request.
 * What the gate buys is that a laptop left open on an issuer console does not
 * hand a passer-by the ability to publish degrees.
 */

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

import { addChainParams, CHAIN_ID, CHAIN_ID_HEX } from "@/lib/chain";

/** The slice of EIP-1193 this app uses. Typed locally so the project does not
 *  take on a wallet SDK to read one property and call three methods. */
interface Eip1193Provider {
  request(args: { method: string; params?: unknown[] | object }): Promise<unknown>;
  on?(event: string, handler: (...args: never[]) => void): void;
  removeListener?(event: string, handler: (...args: never[]) => void): void;
  isMetaMask?: boolean;
}

declare global {
  interface Window {
    ethereum?: Eip1193Provider;
  }
}

export type WalletStatus =
  /** Still asking the extension what it already knows. */
  | "detecting"
  /** No injected provider at all — MetaMask is not installed. */
  | "unavailable"
  /** Installed, but this site has no approved accounts. */
  | "disconnected"
  /** Connected, but the wallet is pointed at a different network. */
  | "wrong-network"
  | "connected";

interface WalletContextValue {
  status: WalletStatus;
  address: string | null;
  chainId: number | null;
  /** Set when a connect or switch attempt failed, for display. */
  error: string | null;
  connecting: boolean;
  connect: () => Promise<void>;
  switchNetwork: () => Promise<void>;
  disconnect: () => void;
}

const WalletContext = createContext<WalletContextValue | null>(null);

/**
 * Remembers that this browser has connected before, so a page reload restores
 * the session silently instead of firing a popup on every navigation.
 *
 * It is a hint, never an authority: the actual check is `eth_accounts`, which
 * returns nothing if permission was revoked in MetaMask. Forging this key gets
 * an attacker a console that fails its first request.
 */
const STORAGE_KEY = "aafnopraman.wallet.connected";

function provider(): Eip1193Provider | null {
  return typeof window === "undefined" ? null : (window.ethereum ?? null);
}

function parseChainId(value: unknown): number | null {
  if (typeof value === "string") return Number.parseInt(value, 16);
  if (typeof value === "number") return value;
  return null;
}

/** MetaMask surfaces a `code`; anything else is an unexpected failure. */
function walletErrorMessage(caught: unknown, fallback: string): string {
  const code = (caught as { code?: number } | null)?.code;
  if (code === 4001) return "You dismissed the MetaMask prompt.";
  if (code === -32002) return "MetaMask is already asking — check the extension window.";
  const message = (caught as { message?: string } | null)?.message;
  return typeof message === "string" && message ? message : fallback;
}

export function WalletProvider({ children }: { children: React.ReactNode }) {
  const [address, setAddress] = useState<string | null>(null);
  const [chainId, setChainId] = useState<number | null>(null);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [connecting, setConnecting] = useState(false);

  /**
   * Restore silently on mount.
   *
   * `eth_accounts` never prompts — it reports what the user has already
   * approved. `eth_requestAccounts` is the one that opens the popup, and it
   * belongs behind a click, not behind a page load.
   */
  useEffect(() => {
    let cancelled = false;

    /**
     * Every state write below lands in a `.then`/`.finally` callback rather
     * than in the effect body. That is not stylistic: React's compiler lint
     * rejects a synchronous `setState` inside an effect, and the no-provider
     * case is the tempting one to answer immediately — `window.ethereum` is
     * either there or it is not. Answering it through the same promise keeps
     * one code path and keeps the rule satisfied.
     */
    const detect = async () => {
      const injected = provider();
      if (!injected) return null;
      const [accounts, currentChain] = await Promise.all([
        injected.request({ method: "eth_accounts" }) as Promise<string[]>,
        injected.request({ method: "eth_chainId" }),
      ]);
      return { accounts, currentChain };
    };

    detect()
      .then((result) => {
        if (cancelled || !result) return;
        const remembered =
          typeof window !== "undefined" && window.localStorage.getItem(STORAGE_KEY) === "1";
        // Both conditions matter: permission can be revoked in MetaMask without
        // this app hearing about it, and the storage hint can outlive it.
        if (remembered && result.accounts.length > 0) setAddress(result.accounts[0] ?? null);
        setChainId(parseChainId(result.currentChain));
      })
      .catch(() => {
        // A provider that throws on a read is one we cannot use. The gate then
        // offers to connect, which surfaces the real error against a click.
      })
      .finally(() => {
        if (!cancelled) setReady(true);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  // Wallet-side changes: a different account selected, or a different network.
  useEffect(() => {
    const injected = provider();
    if (!injected?.on) return;

    const onAccounts = (...args: never[]) => {
      const accounts = args[0] as unknown as string[];
      const next = accounts?.[0] ?? null;
      setAddress(next);
      // Disconnecting every site from inside MetaMask must clear the hint too,
      // or the next load tries to restore a permission that no longer exists.
      if (!next && typeof window !== "undefined") window.localStorage.removeItem(STORAGE_KEY);
    };

    const onChain = (...args: never[]) => setChainId(parseChainId(args[0]));

    injected.on("accountsChanged", onAccounts);
    injected.on("chainChanged", onChain);
    return () => {
      injected.removeListener?.("accountsChanged", onAccounts);
      injected.removeListener?.("chainChanged", onChain);
    };
  }, []);

  const connect = useCallback(async () => {
    const injected = provider();
    if (!injected) {
      setError("No Ethereum wallet was found in this browser.");
      return;
    }

    setConnecting(true);
    setError(null);
    try {
      const accounts = (await injected.request({ method: "eth_requestAccounts" })) as string[];
      const next = accounts[0] ?? null;
      setAddress(next);
      setChainId(parseChainId(await injected.request({ method: "eth_chainId" })));
      if (next && typeof window !== "undefined") window.localStorage.setItem(STORAGE_KEY, "1");
    } catch (caught) {
      setError(walletErrorMessage(caught, "Could not connect to MetaMask."));
    } finally {
      setConnecting(false);
    }
  }, []);

  const switchNetwork = useCallback(async () => {
    const injected = provider();
    if (!injected) return;

    setError(null);
    try {
      await injected.request({
        method: "wallet_switchEthereumChain",
        params: [{ chainId: CHAIN_ID_HEX }],
      });
    } catch (caught) {
      // 4902 — the wallet has never heard of this network. Offer to add it
      // rather than telling the user to configure an RPC by hand.
      if ((caught as { code?: number } | null)?.code === 4902) {
        try {
          await injected.request({
            method: "wallet_addEthereumChain",
            params: [addChainParams()],
          });
          return;
        } catch (addFailed) {
          setError(walletErrorMessage(addFailed, "Could not add the network to MetaMask."));
          return;
        }
      }
      setError(walletErrorMessage(caught, "Could not switch network."));
    }
  }, []);

  /** Local only. There is no way to make a wallet forget a site from script —
   *  `wallet_revokePermissions` is not universally supported — so this clears
   *  our own state and the gate reappears. */
  const disconnect = useCallback(() => {
    setAddress(null);
    setError(null);
    if (typeof window !== "undefined") window.localStorage.removeItem(STORAGE_KEY);
  }, []);

  const status: WalletStatus = !ready
    ? "detecting"
    : !provider()
      ? "unavailable"
      : !address
        ? "disconnected"
        : chainId !== CHAIN_ID
          ? "wrong-network"
          : "connected";

  const value = useMemo<WalletContextValue>(
    () => ({ status, address, chainId, error, connecting, connect, switchNetwork, disconnect }),
    [status, address, chainId, error, connecting, connect, switchNetwork, disconnect],
  );

  return <WalletContext.Provider value={value}>{children}</WalletContext.Provider>;
}

export function useWallet(): WalletContextValue {
  const context = useContext(WalletContext);
  if (!context) throw new Error("useWallet must be used inside <WalletProvider>.");
  return context;
}
