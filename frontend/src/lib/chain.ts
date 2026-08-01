/**
 * The network this deployment anchors to, and how to link into it.
 *
 * Every value is read from `NEXT_PUBLIC_*` at build time, because the browser
 * is what needs them: the wallet gate asks MetaMask to switch to this chain,
 * and the consoles link transaction hashes into this explorer.
 *
 * ## Sepolia, and why the chain id has to match the backend
 *
 * The backend signs and submits every anchoring transaction itself, with the
 * organisation's custodial key — `CHAIN_ID` in `backend/.env` is what goes into
 * those transactions. The value here is only ever used to tell a member of
 * staff which network to be on. If the two disagree, nothing errors: the
 * console cheerfully confirms the wallet is on the right chain while the
 * backend writes to a different one, and the explorer link resolves to a
 * transaction that does not exist. Keeping them equal is a deployment
 * responsibility no code here can enforce.
 */

/** Falls back to Sepolia rather than to a local node: a misconfigured build
 *  should point at the public network people can actually check, not at a
 *  127.0.0.1 that silently works on one laptop. */
export const CHAIN_ID = Number(process.env.NEXT_PUBLIC_CHAIN_ID ?? 11155111);

export const CHAIN_NAME = process.env.NEXT_PUBLIC_CHAIN_NAME ?? "Sepolia";

export const RPC_URL =
  process.env.NEXT_PUBLIC_RPC_URL ?? "https://ethereum-sepolia-rpc.publicnode.com";

/** Empty for a local node — Hardhat has no explorer. */
export const EXPLORER_URL = (process.env.NEXT_PUBLIC_EXPLORER_URL ?? "").replace(/\/$/, "");

/** MetaMask's `wallet_switchEthereumChain` takes hex, not decimal. */
export const CHAIN_ID_HEX = `0x${CHAIN_ID.toString(16)}`;

export function explorerTxUrl(hash: string): string | null {
  return EXPLORER_URL && hash ? `${EXPLORER_URL}/tx/${hash}` : null;
}

export function explorerAddressUrl(address: string): string | null {
  return EXPLORER_URL && address ? `${EXPLORER_URL}/address/${address}` : null;
}

/**
 * What to hand `wallet_addEthereumChain` when a wallet has never heard of this
 * network. Sepolia ships in MetaMask by default, so in practice this only fires
 * for a local Hardhat node or a wallet with testnets hidden.
 */
export function addChainParams() {
  return {
    chainId: CHAIN_ID_HEX,
    chainName: CHAIN_NAME,
    nativeCurrency: { name: "Ether", symbol: "ETH", decimals: 18 },
    rpcUrls: [RPC_URL],
    ...(EXPLORER_URL ? { blockExplorerUrls: [EXPLORER_URL] } : {}),
  };
}
