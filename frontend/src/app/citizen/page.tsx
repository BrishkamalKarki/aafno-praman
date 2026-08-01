"use client";

import { OfferCard } from "@/components/citizen/offer-card";
import {
  ActionGrid,
  ActionTile,
  EmptyState,
  ListCard,
  ListRow,
  SectionHeader,
  StatGrid,
  StatTile,
  StatusPill,
} from "@/components/ui/dashboard";
import { ErrorState, LoadingRows, LoadingStats } from "@/components/ui/form";
import { errorMessage } from "@/lib/api/errors";
import { useAccessLog, useOffers, usePassport, useShareLinks } from "@/lib/api/hooks";
import { pillFor, recordTitle, timeAgo } from "@/lib/api/types";

/**
 * The citizen's home.
 *
 * Pending confirmations come first, above the fold, before anything else. A
 * credential sits in limbo until its subject accepts it — nothing is anchored
 * without consent — so an unanswered confirmation is the only thing on this page
 * that blocks something real.
 */
export default function CitizenDashboard() {
  const passport = usePassport();
  const offers = useOffers();
  const accessLog = useAccessLog();
  const shareLinks = useShareLinks();

  const records = passport.data?.records ?? [];
  // Only what the holder has actually accepted belongs under "my credentials".
  // Offers have their own section above; listing them in both would suggest a
  // degree they have not agreed to is already theirs.
  const confirmed = records.filter((record) => record.status !== "OFFERED");
  const activeLinks = (shareLinks.data ?? []).filter((link) => link.is_active).length;

  return (
    <div className="mx-auto w-full max-w-5xl space-y-8">
      {(offers.data?.length ?? 0) > 0 && (
        <section aria-labelledby="pending" className="space-y-3">
          <h2 id="pending" className="mb-3 text-sm font-semibold tracking-tight">
            Waiting for you
          </h2>
          {offers.data?.map((offer) => (
            <OfferCard key={offer.id} offer={offer} />
          ))}
        </section>
      )}

      {passport.isPending ? (
        <LoadingStats />
      ) : passport.isError ? (
        <ErrorState
          message={errorMessage(passport.error)}
          onRetry={() => void passport.refetch()}
        />
      ) : (
        <StatGrid>
          <StatTile
            label="Credentials"
            value={passport.data?.summary.issued ?? 0}
            tone="verified"
          />
          <StatTile
            label="Awaiting you"
            value={offers.data?.length ?? 0}
            tone="revoked"
            hint="Nothing is on chain until you answer"
          />
          <StatTile label="Active share links" value={activeLinks} tone="brand" />
          <StatTile label="Times checked" value={accessLog.data?.length ?? 0} />
        </StatGrid>
      )}

      <section aria-labelledby="actions">
        <h2 id="actions" className="mb-3 text-sm font-semibold tracking-tight">
          Quick actions
        </h2>
        <ActionGrid>
          <ActionTile
            href="/citizen/shares/new"
            label="Create a share link"
            description="Send proof to an employer"
            icon="link"
            primary
          />
          <ActionTile
            href="/citizen/access-log"
            label="Who checked me"
            description="Every verification of your records"
            icon="activity"
          />
          <ActionTile href="/citizen/credentials" label="All credentials" icon="shield-check" />
          <ActionTile href="/citizen/profile" label="Profile & contact" icon="user" />
        </ActionGrid>
      </section>

      <div className="grid gap-6 lg:grid-cols-2">
        <section aria-labelledby="my-credentials">
          <SectionHeader title="My credentials" href="/citizen/credentials" />
          <h2 id="my-credentials" className="sr-only">
            My credentials
          </h2>

          {passport.isPending ? (
            <LoadingRows />
          ) : confirmed.length === 0 ? (
            <EmptyState
              icon="shield-check"
              title="Nothing here yet"
              description="When a college or employer issues you a credential, it appears here for you to confirm."
            />
          ) : (
            <ListCard>
              {confirmed.slice(0, 5).map((record) => (
                <ListRow
                  key={record.id}
                  title={recordTitle(record)}
                  meta={`${record.issuer_name} · ${timeAgo(record.issued_at ?? record.created_at)}`}
                  trailing={<StatusPill state={pillFor(record.status)} />}
                />
              ))}
            </ListCard>
          )}
        </section>

        <section aria-labelledby="access-log">
          <SectionHeader title="Who checked your credentials" href="/citizen/access-log" />
          <h2 id="access-log" className="sr-only">
            Who checked your credentials
          </h2>

          {accessLog.isPending ? (
            <LoadingRows />
          ) : (accessLog.data?.length ?? 0) === 0 ? (
            <EmptyState
              icon="activity"
              title="Nobody yet"
              description="When an employer verifies one of your credentials, it is listed here."
            />
          ) : (
            <ListCard>
              {accessLog.data?.slice(0, 5).map((entry) => (
                <ListRow
                  key={entry.id}
                  title={entry.verifier}
                  meta={`${entry.credential} · ${timeAgo(entry.created_at)}`}
                />
              ))}
            </ListCard>
          )}

          {/* Anonymous scans are listed but never located. Storing the IP of
              everyone who looked a citizen up would build a surveillance record
              of recruiters, which is not a trade this platform makes. */}
          <p className="mt-2 text-xs text-text-subtle">
            Employers who look you up while signed in are named. Anonymous QR scans are shown
            without any location or device information.
          </p>
        </section>
      </div>
    </div>
  );
}
