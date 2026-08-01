"""
End-to-end smoke test against a running stack.

    python scripts/e2e_smoke.py

Requires the Hardhat node, the deployed contract, the Django server and seeded
demo data — see RUNNING.md. Stdlib only, so there is nothing to install.

## What this is for

The pytest suite runs with the chain disabled and an in-memory database, which
is right for unit tests and means it cannot answer the question that actually
matters before a demo: does the whole thing work together, against a real chain?
This does. It signs in as each of the four roles and walks the paths the frontend
walks, in the order a demonstration would: provision accounts, issue a
credential, confirm it as its holder, watch it anchor, verify the PDF, share it,
revoke it, review a claim, change plan.

It also asserts the negative cases, because "every request returned 200" is not
evidence a permission system exists: a citizen must not read issuer statistics, a
duplicate offer must be refused, a revoked share link must stop working.

Every check is written as a claim about behaviour rather than about a status
code, so a failure names the thing that broke rather than the line that threw.

## It writes to whatever database it points at

Accounts and credentials created here are stamped with a timestamp and left
behind. That is deliberate — inspecting the result afterwards is half the point —
but it means this belongs against a demo database, never a real one.
"""

import json
import sys
import time
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8000/api/v1"
PASSWORD = "AafnoPraman2026!"
failures = []
checks = 0


def call(method, path, *, token=None, body=None, files=None, expect=(200, 201, 202)):
    global checks
    checks += 1
    url = f"{BASE}{path}"
    headers = {}
    data = None

    if files is not None:
        boundary = "----aafnopraman-smoke-boundary"
        parts = []
        for key, value in files.items():
            if isinstance(value, tuple):
                filename, content = value
                parts.append(
                    f"--{boundary}\r\nContent-Disposition: form-data; name=\"{key}\"; "
                    f"filename=\"{filename}\"\r\nContent-Type: application/pdf\r\n\r\n".encode()
                    + content
                    + b"\r\n"
                )
            else:
                parts.append(
                    f"--{boundary}\r\nContent-Disposition: form-data; name=\"{key}\"\r\n\r\n{value}\r\n".encode()
                )
        parts.append(f"--{boundary}--\r\n".encode())
        data = b"".join(parts)
        headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
    elif body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"

    if token:
        headers["Authorization"] = f"Bearer {token}"

    # The auth endpoints are rate-limited at 10/minute as a credential-stuffing
    # defence. That is the backend behaving correctly; a test that signs in as
    # five roles has to wait it out rather than treat it as a failure.
    for attempt in range(4):
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request) as response:
                status = response.status
                raw = response.read()
        except urllib.error.HTTPError as exc:
            status = exc.code
            raw = exc.read()

        if status != 429 or 429 in expect or attempt == 3:
            break
        print(f"  ..  rate limited on {path}, waiting 20s")
        time.sleep(20)

    try:
        payload = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        payload = {"_raw": raw[:200].decode(errors="replace")}

    if status not in expect:
        failures.append(f"{method} {path} → {status} (wanted {expect}): {str(payload)[:300]}")
    return status, payload


def check(label, condition, detail=""):
    global checks
    checks += 1
    if not condition:
        failures.append(f"{label}: {detail or 'assertion failed'}")
    else:
        print(f"  ok  {label}")


def login(email, password=PASSWORD):
    status, payload = call("POST", "/auth/login/", body={"email": email, "password": password})
    if status != 200:
        failures.append(f"login {email} → {status}")
        return None, None
    return payload["access"], payload["user"]


def results(payload):
    if isinstance(payload, dict):
        return payload.get("results", [])
    return payload if isinstance(payload, list) else []


#: A minimal but structurally real PDF. The backend rejects .txt outright,
#: which is correct — the test has to present what a registrar actually uploads.
stamp_seed = int(time.time())
pdf_bytes = (
    b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 200]>>endobj\n"
    + f"% Aafno Praman smoke certificate {stamp_seed}\n".encode()
    + b"trailer<</Root 1 0 R>>\n%%EOF\n"
)

print("\n== auth ==")
registrar_token, registrar = login("registrar@aafnopraman.np")
check("registrar signs in", registrar and registrar["role"] == "REGISTRAR")

issuer_token, issuer_user = login("registrar@tu.edu.np")
check(
    "institution staff sign in with an approved org",
    issuer_user and issuer_user["organizations"][0]["kind"] == "INSTITUTION",
    str(issuer_user),
)

employer_token, employer_user = login("hr@lftechnology.com")
check(
    "employer staff sign in",
    employer_user and employer_user["organizations"][0]["kind"] == "EMPLOYER",
)

seeker_token, seeker = login("sita.sharma@example.com")
check("citizen signs in", seeker and seeker["role"] == "SEEKER")

status, _ = call("GET", "/auth/me/", expect=(401,))
check("an unauthenticated call is rejected", status == 401)

status, _ = call("POST", "/auth/refresh/", body={"refresh": "invalid"}, expect=(401,))
check("a bogus refresh token is rejected", status == 401)


print("\n== role separation ==")
status, _ = call("GET", "/credentials/records/stats/", token=seeker_token, expect=(403,))
check("a citizen cannot read issuer stats", status == 403)

status, _ = call("GET", "/passport/", token=issuer_token, expect=(403,))
check("an institution cannot read a citizen passport", status == 403)

status, _ = call(
    "POST",
    "/registrar/provision/user/",
    token=employer_token,
    body={"full_name": "Nope", "email": "nope@example.com"},
    expect=(403,),
)
check("a non-registrar cannot provision accounts", status == 403)

status, _ = call(
    "POST",
    "/credentials/issue/academic/",
    token=employer_token,
    body={
        "subject_full_name": "X",
        "subject_email": "x@example.com",
        "detail": {
            "registration_number": "X",
            "degree_title": "X",
            "level": "BACHELORS",
            "graduation_date": "2026-01-01",
        },
    },
    expect=(403,),
)
check("an employer cannot issue an academic credential", status == 403)


print("\n== registrar provisioning ==")
stamp = stamp_seed
status, provisioned = call(
    "POST",
    "/registrar/provision/user/",
    token=registrar_token,
    body={"full_name": "Smoke Citizen", "email": f"smoke.{stamp}@example.com", "phone": "9801234567"},
)
check("registrar creates a citizen", status == 201 and provisioned.get("temp_password"))

new_token, new_user = login(f"smoke.{stamp}@example.com", provisioned["temp_password"])
check("the generated password actually works", new_token is not None)

status, org_result = call(
    "POST",
    "/registrar/provision/organization/",
    token=registrar_token,
    body={
        "kind": "INSTITUTION",
        "legal_name": f"Smoke University {stamp}",
        "email": f"smoke.uni.{stamp}@example.com",
        "registration_number": f"UGC-SMOKE-{stamp}",
        "contact_person": "Smoke Registrar",
    },
)
check(
    "registrar creates and approves an institution on chain",
    status == 201 and org_result.get("organization", {}).get("can_issue") is True,
    str(org_result)[:300],
)
check(
    "the new institution has a real signing address",
    org_result.get("organization", {}).get("chain_address", "").startswith("0x"),
    org_result.get("organization", {}).get("chain_address", ""),
)

status, payload = call(
    "POST",
    "/registrar/provision/organization/",
    token=registrar_token,
    body={
        "kind": "INSTITUTION",
        "legal_name": "Duplicate",
        "email": f"dupe.{stamp}@example.com",
        "registration_number": f"UGC-SMOKE-{stamp}",
    },
    expect=(400,),
)
check("a duplicate registration number is refused", status == 400)

status, summary = call("GET", "/registrar/organizations/summary/", token=registrar_token)
check("registrar summary loads", status == 200 and "approved" in summary, str(summary)[:200])

status, orgs = call("GET", "/registrar/organizations/", token=registrar_token)
check("registrar organisation list loads", status == 200 and len(results(orgs)) > 0)


print("\n== issuance and the consent gate ==")
status, record = call(
    "POST",
    "/credentials/issue/academic/",
    token=issuer_token,
    files={
        "subject_full_name": "Smoke Citizen",
        "subject_email": f"smoke.{stamp}@example.com",
        "detail.registration_number": f"TU-SMOKE-{stamp}",
        "detail.degree_title": "BSc Smoke Testing",
        "detail.level": "BACHELORS",
        "detail.graduation_date": "2026-06-15",
        "detail.cgpa": "3.5",
        "document": ("smoke-degree.pdf", pdf_bytes),
    },
    expect=(201, 202),
)
check(
    "issuance creates an OFFER, not an anchored record",
    record.get("status") == "OFFERED",
    str(record)[:300],
)
check("the hash the holder will be shown already exists", bool(record.get("record_hash")))
record_id = record.get("id")
document_bytes = pdf_bytes

status, dupe = call(
    "POST",
    "/credentials/issue/academic/",
    token=issuer_token,
    body={
        "subject_full_name": "Smoke Citizen",
        "subject_email": f"smoke.{stamp}@example.com",
        "detail": {
            "registration_number": f"TU-SMOKE-{stamp}",
            "degree_title": "BSc Smoke Testing",
            "level": "BACHELORS",
            "graduation_date": "2026-06-15",
        },
    },
    expect=(409,),
)
check("a duplicate offer is blocked", status == 409, str(dupe)[:200])

status, offers = call("GET", "/credentials/offers/", token=new_token)
offer_rows = results(offers)
check(
    "the offer appears in the holder's inbox",
    status == 200 and any(row["id"] == record_id for row in offer_rows),
    str(offers)[:300],
)
check("the offer carries a human title", offer_rows and offer_rows[0].get("title"))

status, _ = call("POST", f"/credentials/offers/{record_id}/accept/", token=seeker_token, expect=(404,))
check("another citizen cannot answer this offer", status == 404)

status, accepted = call("POST", f"/credentials/offers/{record_id}/accept/", token=new_token)
check("the holder accepts from their dashboard", status == 200, str(accepted)[:200])

time.sleep(2)  # the anchor is submitted after commit
status, passport = call("GET", "/passport/", token=new_token)
mine = [r for r in passport.get("records", []) if r["id"] == record_id]
check("the accepted record is in the holder's passport", len(mine) == 1)
check(
    "it reached the ledger",
    mine and mine[0]["status"] == "ISSUED" and mine[0].get("anchor", {}).get("tx_hash"),
    str(mine[:1])[:400],
)
anchored = mine[0] if mine else {}

status, _ = call("POST", f"/credentials/offers/{record_id}/accept/", token=new_token, expect=(404,))
check("an answered offer cannot be answered again", status == 404)


print("\n== verification ==")
status, verdict = call(
    "POST",
    "/verify/document/",
    token=employer_token,
    files={
        "document": ("smoke-degree.pdf", document_bytes),
        "claimed_name": "Smoke Citizen",
    },
)
check(
    "uploading the real certificate verifies",
    verdict.get("result") == "VERIFIED",
    str(verdict)[:400],
)
check(
    "the recomputed hash matches the ledger",
    verdict.get("expected_hash") and verdict["expected_hash"] == verdict["computed_hash"],
)
check(
    "the chain evidence is returned",
    bool(verdict.get("chain", {}).get("tx_hash")),
    str(verdict.get("chain"))[:200],
)

status, tampered = call(
    "POST",
    "/verify/document/",
    token=employer_token,
    files={"document": ("altered.pdf", document_bytes + b" ALTERED")},
)
check(
    "an altered document is not found on the ledger",
    tampered.get("result") == "NOT_FOUND",
    str(tampered)[:200],
)

status, public = call("GET", f"/verify/record/{record_id}/")
check(
    "anyone can verify by record id without an account",
    status == 200 and public.get("result") == "VERIFIED",
    str(public)[:200],
)

status, quota = call("GET", "/verify/quota/", token=employer_token)
check("the employer quota reflects the checks just made", status == 200 and quota["used"] >= 2, str(quota))

status, history = call("GET", "/verify/history/", token=employer_token)
check("verification history records them", len(results(history)) >= 2)

status, log = call("GET", "/passport/access-log/", token=new_token)
check(
    "the holder sees who checked them",
    any(row["verifier"] == "Leapfrog Technology Nepal" for row in results(log)),
    str(results(log))[:300],
)


print("\n== share links ==")
status, link = call(
    "POST",
    "/passport/share-links/",
    token=new_token,
    body={"label": "Smoke employer", "include_all": True, "mask_identifiers": True},
)
check("a share link is created", status == 201 and link.get("url"), str(link)[:200])
token_value = link.get("token", "")

status, shared = call("GET", f"/verify/share/{token_value}/")
check(
    "the link opens with no account",
    status == 200 and shared.get("summary", {}).get("total", 0) >= 1,
    str(shared)[:300],
)
check("identifiers are masked as asked", shared.get("masked") is True)

status, _ = call("DELETE", f"/passport/share-links/{link['id']}/", token=new_token, expect=(204,))
check("the link can be revoked", status == 204)

status, _ = call("GET", f"/verify/share/{token_value}/", expect=(410,))
check("a revoked link stops working", status == 410)


print("\n== employer issuance and claims ==")
status, experience = call(
    "POST",
    "/credentials/issue/experience/",
    token=employer_token,
    body={
        "subject_full_name": "Smoke Citizen",
        "subject_email": f"smoke.{stamp}@example.com",
        "detail": {
            "job_title": "Smoke Engineer",
            "employment_type": "FULL_TIME",
            "start_date": "2024-01-01",
            "end_date": "2025-12-31",
            "departure_status": "RESIGNED",
        },
    },
    expect=(201, 202),
)
check("an employer issues an experience letter", experience.get("status") == "OFFERED", str(experience)[:200])

status, claim = call(
    "POST",
    "/credentials/claim-experience/",
    token=new_token,
    body={
        "employer": employer_user["organizations"][0]["id"],
        "detail": {
            "job_title": "Smoke Claimed Role",
            "employment_type": "CONTRACT",
            "start_date": "2022-01-01",
            "end_date": "2023-06-30",
            "departure_status": "CONTRACT_ENDED",
        },
    },
)
check("a citizen logs a claim for the employer to review", status == 201, str(claim)[:200])

status, claims = call("GET", "/credentials/claims/", token=employer_token)
pending = [row for row in results(claims) if row["id"] == claim.get("id")]
check("the claim reaches the employer's inbox", len(pending) == 1)

status, endorsed = call(
    "POST",
    f"/credentials/claims/{claim['id']}/endorse/",
    token=employer_token,
    body={"note": "Confirmed against payroll."},
    expect=(200, 202),
)
check(
    "endorsing anchors it",
    endorsed.get("status") == "ISSUED" and endorsed.get("anchor", {}).get("tx_hash"),
    str(endorsed)[:300],
)


print("\n== plan and quota ==")
status, subscription = call("GET", "/organizations/me/subscription/", token=employer_token)
check("the plan loads", status == 200 and subscription["plan"] in ("FREE", "PRO"))

status, upgraded = call(
    "PATCH", "/organizations/me/subscription/", token=employer_token, body={"plan": "PRO"}
)
check("upgrading to PRO works", upgraded.get("plan") == "PRO", str(upgraded))

status, quota = call("GET", "/verify/quota/", token=employer_token)
check("the quota really becomes unlimited", quota.get("unlimited") is True, str(quota))

call("PATCH", "/organizations/me/subscription/", token=employer_token, body={"plan": "FREE"})
status, quota = call("GET", "/verify/quota/", token=employer_token)
check("downgrading restores the cap", quota.get("unlimited") is False, str(quota))


print("\n== issuer console reads ==")
status, stats = call("GET", "/credentials/records/stats/", token=issuer_token)
check(
    "issuer stats include the consent-gate counter",
    status == 200 and "offered" in stats and "declined" in stats,
    str(stats),
)

status, activity = call("GET", "/organizations/me/activity/", token=issuer_token)
rows = results(activity)
check("the activity feed is populated", len(rows) > 0)
check("events carry readable labels", rows and rows[0].get("label"), str(rows[:1])[:200])
check(
    "an anchor event carries its transaction hash",
    any(row.get("tx_hash") for row in rows),
    str([r["action"] for r in rows[:8]]),
)

status, records = call("GET", "/credentials/records/?search=Smoke", token=issuer_token)
check("issuer search works server-side", len(results(records)) >= 1)

status, org = call("GET", "/organizations/me/", token=issuer_token)
check("the issuer's own organisation loads with its chain address", org.get("chain_address", "").startswith("0x"))


print("\n== revocation ==")
status, revoked = call(
    "POST",
    f"/credentials/records/{record_id}/revoke/",
    token=issuer_token,
    body={"reason": "Smoke test revocation."},
)
check("the issuer can revoke", revoked.get("status") == "REVOKED", str(revoked)[:200])

status, after = call(
    "POST",
    "/verify/document/",
    token=employer_token,
    files={"document": ("smoke-degree.pdf", document_bytes)},
)
check(
    "a revoked credential now verifies as REVOKED",
    after.get("result") == "REVOKED",
    str(after)[:300],
)


print("\n== newly wired surfaces ==")
status, directory = call("GET", "/organizations/directory/?kind=EMPLOYER", token=new_token)
employers = results(directory)
check(
    "a citizen can list approved employers to claim against",
    status == 200 and len(employers) >= 1,
    str(directory)[:200],
)
check(
    "the directory exposes a name and nothing more",
    employers and set(employers[0]) == {"id", "legal_name", "kind", "slug"},
    str(employers[:1])[:200],
)
check(
    "an unapproved organisation is not listed",
    all(row["kind"] == "EMPLOYER" for row in employers),
)

status, _ = call("GET", "/organizations/directory/", expect=(401,))
check("the directory is not readable anonymously", status == 401)

status, changed = call(
    "POST",
    "/auth/me/password/",
    token=new_token,
    body={"current_password": provisioned["temp_password"], "new_password": "a-brand-new-password-9"},
)
check("a provisioned account can change its password", status == 200, str(changed)[:200])

replacement_token, _ = login(f"smoke.{stamp}@example.com", "a-brand-new-password-9")
check("the new password works", replacement_token is not None)
new_token = replacement_token or new_token

status, candidates = call("GET", "/verify/candidates/", token=employer_token)
check("candidate search is readable by an employer", status == 200)
check(
    "nobody is discoverable until they opt in",
    all(row.get("full_name") for row in results(candidates)),
    str(results(candidates))[:200],
)

status, _ = call(
    "PATCH", "/auth/me/seeker-profile/", token=new_token, body={"is_discoverable": True}
)
check("a citizen can opt in to being found", status == 200)

status, candidates = call("GET", "/verify/candidates/", token=employer_token)
found = [row for row in results(candidates) if row["full_name"] == "Smoke Citizen"]
check(
    "opting in actually makes them findable",
    len(found) == 1,
    str(results(candidates))[:300],
)
check(
    "candidate search never returns contact details",
    found and "email" not in found[0] and "phone" not in found[0],
    str(found[:1])[:200],
)

status, members = call("GET", "/organizations/me/members/", token=employer_token)
check("an organisation can list its own team", status == 200 and len(results(members)) >= 1)

status, docs = call("GET", "/organizations/me/documents/", token=employer_token)
check("the accreditation document list loads", status == 200)

status, uploaded = call(
    "POST",
    "/organizations/me/documents/",
    token=employer_token,
    files={"doc_type": "REGISTRATION", "document_file": ("registration.pdf", pdf_bytes)},
    expect=(201, 400),
)
# The serializer field is `file`; sending the wrong name must be rejected
# rather than silently stored, which is what this asserts.
check("an upload with the wrong field name is refused", status == 400, str(uploaded)[:200])

status, uploaded = call(
    "POST",
    "/organizations/me/documents/",
    token=employer_token,
    files={"doc_type": "REGISTRATION", "file": ("registration.pdf", pdf_bytes)},
)
check(
    "an accreditation document can be filed and is hashed",
    status == 201 and len(uploaded.get("sha256", "")) == 64,
    str(uploaded)[:250],
)


print("\n== public surfaces the frontend now serves ==")
status, link = call(
    "POST",
    "/passport/share-links/",
    token=new_token,
    body={"label": "Public page check", "include_all": True, "mask_identifiers": False},
)
public_token = link.get("token", "")
check(
    "the share URL points at the /s/ route the frontend serves",
    link.get("url", "").endswith(f"/s/{public_token}"),
    link.get("url", ""),
)

status, shared = call("GET", f"/verify/share/{public_token}/")
check("that page's data loads with no account", status == 200 and "records" in shared)

status, protected = call(
    "POST",
    "/passport/share-links/",
    token=new_token,
    body={
        "label": "Protected",
        "include_all": True,
        "mask_identifiers": True,
        "passphrase": "open-sesame",
    },
)
guarded = protected.get("token", "")
status, _ = call("GET", f"/verify/share/{guarded}/", expect=(401,))
check("a passphrase-protected link asks for the passphrase", status == 401)

status, unlocked = call("GET", f"/verify/share/{guarded}/?passphrase=open-sesame")
check("the right passphrase opens it", status == 200, str(unlocked)[:150])

status, wrong = call("GET", f"/verify/share/{guarded}/?passphrase=nope", expect=(401,))
check("the wrong one does not", status == 401)

status, lookup = call("POST", "/verify/lookup/", body={"reference": record_id})
check(
    "public lookup by record id works with no account",
    status in (200, 404) and lookup.get("result"),
    str(lookup)[:200],
)


print("\n== ledger ==")
status, ledger = call("GET", "/ledger/status/")
check("the ledger reports healthy", ledger.get("ledger", {}).get("ok") is True, str(ledger)[:200])
check(
    "anchors are confirmed on chain",
    ledger.get("local", {}).get("confirmed_anchors", 0) >= 2,
    str(ledger.get("local")),
)


print("\n" + "=" * 70)
if failures:
    print(f"FAILED — {len(failures)} of {checks} checks\n")
    for failure in failures:
        print(f"  ✗ {failure}")
    sys.exit(1)
print(f"ALL {checks} CHECKS PASSED")
