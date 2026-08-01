# Aafno Praman

**आफ्नो प्रमाण** — "your own proof."

A platform for issuing and verifying academic and employment credentials,
built for an IEEE Ideathon. Universities and employers issue credentials,
citizens hold and share them, and anyone can verify one in seconds — because
the important part (a fingerprint of the record) is anchored on a public
blockchain instead of living in a filing cabinet somewhere.

## Why

Verifying a degree in Nepal today usually means calling the university,
mailing a request, and waiting weeks for a reply. Most employers just skip
it. That gap is exactly what makes a forged transcript worth the risk.

This project tries to close that gap: a university publishes a credential,
the graduate approves it, and it's checkable by anyone in a few seconds —
without needing to trust our word for it, since the record is on-chain.

## How it works, roughly

1. A university or employer issues a credential to someone's account.
2. Nothing goes on-chain yet — it's just an offer. The person has to accept
   it first.
3. Once accepted, a hash of the credential is written to the blockchain.
   Only the hash, never personal data.
4. Anyone can verify a credential — by uploading it, scanning a QR code, or
   opening a share link — and get back one of a few clear answers: verified,
   tampered, revoked, or not found.

## Tech stack

- **Frontend** — Next.js, React, TypeScript, Tailwind CSS, TanStack Query
- **Backend** — Django, Django REST Framework, PostgreSQL
- **Blockchain** — Solidity contracts (Hardhat), deployed to Sepolia testnet
- **Wallets** — MetaMask, for the institution and employer dashboards

## Project structure

```
aafno-praman/
├── frontend/     # Next.js app
├── backend/      # Django API
├── contracts/    # Solidity contracts + Hardhat setup
└── scripts/      # end-to-end smoke test
```

## Getting started

You'll need Node 20+, Python 3.12+, and Postgres (or just use SQLite locally).

**1. Deploy the contract** (or run a local chain)

```bash
cd contracts
npm install
npm run node            # terminal 1, leave running
npm run deploy:local    # terminal 2
```

**2. Backend**

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements/dev.txt
cp .env.example .env    # fill in the three required secrets
python manage.py migrate
python manage.py seed_demo
python manage.py runserver
```

**3. Frontend**

```bash
cd frontend
npm install
cp .env.local.example .env.local
npm run dev
```

Then open [http://localhost:3000](http://localhost:3000).

Full setup notes (including deploying to Sepolia instead of running
locally) are in `RUNNING.md`.

## Demo accounts

Running `seed_demo` creates a few accounts to try things out with. Password
for all of them is `AafnoPraman2026!`.

| Role | Email |
|---|---|
| Registrar | registrar@aafnopraman.np |
| Institution | registrar@tu.edu.np |
| Employer | hr@lftechnology.com |
| Citizen | sita.sharma@example.com |

## Tests

```bash
cd backend && pytest
cd contracts && npx hardhat test
cd frontend && npm run typecheck && npm run lint && npm run build
```

## Status

Built for an IEEE Ideathon submission — this is an MVP, not a production
system. Contributions and feedback welcome.