"use client";

import { Icon } from "@/components/ui/icon";
import { useLedgerStatus } from "@/lib/api/hooks";

/**
 * Says out loud whether the chain is reachable.
 *
 * The platform degrades rather than fails when the node is down: issuance still
 * works, consent still works, and confirmed records queue at PENDING_ANCHOR
 * until the retry command finishes them. That is the correct behaviour, and it
 * is also completely invisible — an issuer would see credentials appear, not
 * anchor, and conclude the product is broken.
 *
 * So the banner appears only when something is actually wrong, and says what is
 * still safe to do. A permanently visible "all systems normal" strip is
 * furniture people stop reading.
 */
export function LedgerBanner() {
  const { data } = useLedgerStatus();
  if (!data || data.ledger.ok) return null;

  const disabled = !data.ledger.enabled;

  return (
    <div
      role="status"
      className="flex items-start gap-2.5 rounded-[var(--radius-card)] border px-4 py-3 text-sm"
      style={{
        backgroundColor: "var(--color-revoked-surface)",
        borderColor: "var(--color-revoked-border)",
      }}
    >
      <Icon name="activity" size={16} className="mt-0.5 shrink-0 text-revoked" />
      <div>
        <p className="font-medium text-text">
          {disabled ? "Ledger anchoring is switched off" : "The ledger is unreachable right now"}
        </p>
        <p className="mt-0.5 text-text-muted">
          Issuing still works and nothing is lost. Confirmed credentials wait as{" "}
          <span className="font-medium">Pending anchor</span> and are written automatically once
          the node is back.
          {data.local.pending_anchors > 0 && (
            <> {data.local.pending_anchors} are queued.</>
          )}
        </p>
      </div>
    </div>
  );
}
