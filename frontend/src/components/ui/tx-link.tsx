import { explorerAddressUrl, explorerTxUrl } from "@/lib/chain";

/**
 * A transaction hash or address, linked into the block explorer when there is
 * one to link to.
 *
 * The whole argument for anchoring to a public chain is that a verifier does
 * not have to trust this application. A hash rendered as inert monospace text
 * makes that argument and then withholds the means to act on it — the reader
 * has to know what an explorer is, find one, and paste. So the hash is a link
 * wherever `NEXT_PUBLIC_EXPLORER_URL` is set.
 *
 * Against a local Hardhat node it is set to nothing, and the component falls
 * back to plain text rather than producing a link to a page that cannot exist.
 * A dead link on the evidence is worse than no link.
 */
export function TxLink({
  hash,
  short,
  className = "",
}: {
  hash: string;
  /** Display text, if the caller has already abbreviated it. */
  short?: string;
  className?: string;
}) {
  const href = explorerTxUrl(hash);
  const label = short ?? hash;

  if (!href) return <span className={`font-mono ${className}`}>{label}</span>;

  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className={`font-mono underline decoration-dotted underline-offset-2 hover:text-brand ${className}`}
      title="View this transaction on the block explorer"
    >
      {label}
    </a>
  );
}

export function AddressLink({
  address,
  short,
  className = "",
}: {
  address: string;
  short?: string;
  className?: string;
}) {
  const href = explorerAddressUrl(address);
  const label = short ?? address;

  if (!href) return <span className={`font-mono ${className}`}>{label}</span>;

  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className={`font-mono underline decoration-dotted underline-offset-2 hover:text-brand ${className}`}
      title="View this address on the block explorer"
    >
      {label}
    </a>
  );
}
