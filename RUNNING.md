# Running Aafno Praman

Four processes: a chain, a database, the API, and the web app. Start them in
this order — the backend refuses to approve an issuer while the chain is
unreachable, which is deliberate (an organisation marked approved in the
database but absent from the contract fails at its first issuance with an opaque
revert).

Node 20.9+ and Python 3.12 are required.

---

## Which chain?

This repo is configured for **Sepolia**, Ethereum's public test network, so
anchored credentials can be checked on `sepolia.etherscan.io` by someone who
does not trust this API. That needs a funded account.

**For a local demo with no faucet and no waiting**, change three lines in
`backend/.env`:

```ini
CHAIN_RPC_URL=http://127.0.0.1:8545
CHAIN_ID=31337
CHAIN_CONTRACT_ADDRESS=0x5FbDB2315678afecb367f032d93F642f64180aa3
```

and the matching two in `frontend/.env.local`:

```ini
NEXT_PUBLIC_CHAIN_ID=31337
NEXT_PUBLIC_EXPLORER_URL=
```

Everything else is identical — the chain is addressed entirely through those
variables. Leaving `NEXT_PUBLIC_EXPLORER_URL` empty makes the UI render
transaction hashes as plain text rather than linking to an explorer that has
never heard of your local node.

> If the frontend's chain id and the backend's disagree, nothing errors. The
> console tells staff to switch to one network while the backend anchors to
> another, and the explorer link resolves to a transaction that does not exist.

---

## 1. Chain

### Sepolia

```bash
cd contracts
npm install
export DEPLOYER_PRIVATE_KEY=0x…      # an account you generated
npm run deploy:sepolia
```

The deployer needs Sepolia ETH — roughly 0.02 for the deploy, plus whatever the
registrar hands out to issuers. `sepoliafaucet.com` and
`faucet.quicknode.com/ethereum/sepolia` both work.

Put the printed address into `backend/.env` as `CHAIN_CONTRACT_ADDRESS`, and the
same deployer key as `CHAIN_REGISTRAR_PRIVATE_KEY` — that account is what
approves issuers and tops up their gas.

> `CHAIN_GAS_TOPUP_WEI` is set to 0.005 ETH per issuer, sized for faucet-scale
> balances. The settings default is 0.1, which is fine against a Hardhat node
> holding 10,000 ETH and will empty a real faucet balance on the third
> organisation you approve.

### Local Hardhat

```bash
cd contracts
npm install
npm run node                 # terminal 1 — leave running
npm run deploy:local         # terminal 2
```

The address is deterministic on a fresh node —
`0x5FbDB2315678afecb367f032d93F642f64180aa3` — so it usually only needs setting
once.

`deploy:*` writes the address to `deployments/`, and the ABI into
`backend/apps/ledger/abi/`.

## 2. Database

Postgres, or SQLite if you would rather not run one:

```bash
# backend/.env
DATABASE_URL=postgres://veridock:veridock@localhost:5432/veridock
# or
DATABASE_URL=sqlite:///db.sqlite3
```

> The role and database are still named `veridock`. Renaming them is a migration
> with downtime, not a string change, and the name is not user-visible.

## 3. Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements/dev.txt
cp .env.example .env         # then fill in the three REQUIRED secrets
python manage.py migrate
python manage.py seed_demo   # needs the chain up; add --skip-chain-check to skip
python manage.py runserver
```

`.env` has no defaults for `DJANGO_SECRET_KEY`, `KEY_ENCRYPTION_KEY` or
`NATIONAL_ID_PEPPER`, and it will not boot without them. That is intentional: a
predictable `KEY_ENCRYPTION_KEY` makes every issuer's signing key recoverable,
and a predictable pepper turns the citizenship lookup column into a searchable
list of citizens. The generator command for each is written next to it in
`.env.example`.

## 4. Frontend

```bash
cd frontend
npm install
cp .env.local.example .env.local
npm run dev
```

Open <http://localhost:3000>.

---

## MetaMask

The **institution and employer consoles require MetaMask**, connected to the
network in `NEXT_PUBLIC_CHAIN_ID`. Citizens and the registrar do not — requiring
a browser extension to accept your own degree would exclude most of the people
this platform is for.

Connecting confirms *who is operating the console*. It does not sign anything:
credentials are signed with the organisation's key, which the platform generates
and holds, and no member of staff is ever asked to approve a transaction or pay
gas. If the wallet is on the wrong network the console offers to switch it, and
to add it if MetaMask has never seen it.

For a local Hardhat node, import one of its printed test accounts into MetaMask
— or just let the gate's "switch network" button add the network for you.

---

## Demo accounts

`seed_demo` creates these. All use the password **`AafnoPraman2026!`**.

| Role | Email | What they see |
|---|---|---|
| Registrar | `registrar@aafnopraman.np` | `/admin` — provision accounts, approve issuers |
| Institution | `registrar@tu.edu.np` | `/issuer` — issue degrees, ledger activity |
| Employer | `hr@lftechnology.com` | `/employer` — verify, issue experience letters |
| Employer | `people@fusemachines.com` | a second employer, with a claim waiting |
| Citizen | `sita.sharma@example.com` | `/citizen` — credentials, share links, access log |
| Citizen | `bikash.thapa@example.com` | |
| Citizen | `anjali.gurung@example.com` | one claim pending endorsement |

Everyone signs in at `/login`; where they land is decided by what the account is,
not by which tile they clicked on the way in.

Seeded credentials arrive as **offers**. Nothing is on chain until the holder
accepts one — sign in as Sita and accept from her dashboard to watch a record
move from *Awaiting confirmation* to *Anchored* with a real transaction hash.

Confirmation emails print to the backend console in development, so the emailed
`/confirm/<token>` link is in that terminal.

---

## Public pages (no account)

| Route | What it is |
|---|---|
| `/verify` | Check a credential by record id or fingerprint — the QR-code destination |
| `/s/<token>` | A shared passport. Every share link a citizen creates points here |
| `/confirm/<token>` | The "is this you?" link from a credential email |

## A five-minute walkthrough

1. **Registrar** (`/admin`) → *Create an institution*. It is approved and
   registered on chain in the same request, and you are handed a temporary
   password once.
2. **Institution** (`/issuer/issue`) → connect MetaMask, then issue a degree to
   a citizen's email. Nothing anchors; the graduate is asked first.
3. **Citizen** (`/citizen`) → the offer is at the top of the dashboard with the
   exact fingerprint that will be published. Accept it, and it anchors.
4. **Employer** (`/employer/verify`) → upload the same PDF. VERIFIED, with the
   transaction hash — linked to Etherscan — and both hashes shown so the result
   can be checked independently. The quota meter moves.
5. **Citizen** (`/citizen/access-log`) → the employer is named, and the check
   they just ran is listed.
6. **Citizen** (`/citizen/shares/new`) → create a share link, copy it, open it in
   a private window. That is `/s/<token>`, and it works without an account.
7. **Institution** (`/issuer/history`) → revoke it with a reason. Verify the same
   PDF again: REVOKED, with the reason attached.

Two flows worth seeing separately:

* **A job with no letter.** Citizen → *Log a past job*, pick an employer, submit.
  Employer → *Claims to review*, confirm it. It anchors under the company's name.
* **Being findable.** Citizen → *Account*, switch on discoverability. Employer →
  *Find candidates*. Off by default, and no contact details are ever returned.

---

## Tests

```bash
cd backend && pytest                  # 140 tests, no chain or database needed
cd contracts && npx hardhat test      # 33 tests
cd frontend && npm run typecheck && npm run lint && npm run build
python scripts/e2e_smoke.py           # 146 checks against the running stack
```

The pytest suite runs with the chain disabled and an in-memory SQLite database.
`scripts/e2e_smoke.py` is the counterpart that exercises the real thing — a live
chain, real anchoring, real metering — and is what to run before a demo.

> The unit suite runs on SQLite, which silently ignores `select_for_update`. Any
> change touching row locking has to be exercised against Postgres before it is
> called done; see the note at the top of `backend/tests/conftest.py`.

---

## When the chain is down

Nothing breaks, and the UI says so rather than pretending. Issuing and consent
keep working; confirmed credentials wait in `PENDING_ANCHOR` and are written when
the node returns. A banner appears on the issuer, employer and admin dashboards,
and each record shows *Pending anchor* until it is written.

The same applies before you have deployed a contract at all: `/ledger/status/`
answers with `ok: false` and the reason, and the banner explains it.

To finish a backlog by hand:

```bash
python manage.py anchor_pending
```

Two things deliberately refuse to proceed without the chain, because completing
them off-chain would leave a broken state that is worse than a failed request:
approving an organisation, and reinstating a suspended one. Both would otherwise
produce an issuer the contract rejects, appearing active in the UI while unable
to issue anything.
