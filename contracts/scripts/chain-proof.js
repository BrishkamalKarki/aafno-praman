/**
 * chain-proof.js — independent evidence that this platform is really on-chain.
 *
 * Run this against a live node and it performs a full round trip using nothing
 * but ethers and the deployed contract: approve an issuer, anchor a credential,
 * read it back, then alter one character of the credential and watch the ledger
 * refuse to recognise it.
 *
 * It deliberately does not import a single line of the Django backend. If the
 * backend were faking its blockchain integration, this script would still work
 * and would still disagree with it — which is exactly what makes it evidence
 * rather than decoration.
 *
 *   npx hardhat run scripts/chain-proof.js --network localhost
 */
const fs = require("node:fs");
const path = require("node:path");
const hre = require("hardhat");

const line = (label, value) => console.log(`  ${label.padEnd(22)} ${value}`);

async function main() {
  const { ethers } = hre;
  const deploymentPath = path.join(
    __dirname,
    "..",
    "deployments",
    `${hre.network.name}.json`
  );

  if (!fs.existsSync(deploymentPath)) {
    throw new Error(
      `No deployment found at ${deploymentPath}. Run the deploy script first.`
    );
  }

  const deployment = JSON.parse(fs.readFileSync(deploymentPath, "utf8"));
  const [registrar, university] = await ethers.getSigners();
  const registry = await ethers.getContractAt(
    "CredentialRegistry",
    deployment.address
  );

  console.log("\n=== 1. CHAIN IDENTITY ============================================\n");
  const network = await ethers.provider.getNetwork();
  line("chain id", network.chainId.toString());
  line("contract", deployment.address);
  line("block height", await ethers.provider.getBlockNumber());
  line("on-chain registrar", await registry.registrar());

  // -- 2. Onboard an issuer -------------------------------------------------
  console.log("\n=== 2. REGISTRAR APPROVES AN ISSUER ==============================\n");
  const alreadyApproved = await registry.canAnchor(university.address);
  if (!alreadyApproved) {
    const approveTx = await registry
      .connect(registrar)
      .approveIssuer(university.address, 1 /* Institution */, "Tribhuvan University");
    const approveReceipt = await approveTx.wait();
    line("issuer address", university.address);
    line("tx hash", approveReceipt.hash);
    line("block", approveReceipt.blockNumber);
    line("gas used", approveReceipt.gasUsed.toString());
  } else {
    line("issuer address", `${university.address} (already approved)`);
  }
  line("canAnchor()", await registry.canAnchor(university.address));

  // -- 3. Anchor a real credential -----------------------------------------
  console.log("\n=== 3. INSTITUTION ANCHORS A CREDENTIAL ==========================\n");

  // Canonical form, matching backend/apps/ledger/canonical.py: domain tag,
  // sorted keys, no whitespace, NFC strings, numbers as fixed-precision strings.
  const credential = {
    academic: {
      cgpa: "3.21",
      degree_title: "Bachelor of Science in Computer Science and IT",
      graduation_date: "2026-06-15",
      level: "BACHELORS",
      registration_number: "TU-2078-CSIT-041",
    },
    issuer_address: university.address.toLowerCase(),
    record_id: "6f1a9c74-6d2f-4e8b-9f3d-2c5a7b1e4d80",
    schema: "1.0",
    subject_name: "Sita Sharma",
    type: "ACADEMIC",
  };

  const canonical = `VERIDOCK-RECORD-V1\n${JSON.stringify(credential)}`;
  const recordHash = ethers.keccak256(ethers.toUtf8Bytes(canonical));

  line("subject", credential.subject_name);
  line("CGPA on certificate", credential.academic.cgpa);
  line("keccak256 hash", recordHash);

  const anchored = await registry.isAnchored(recordHash);
  if (!anchored) {
    const anchorTx = await registry.connect(university).anchor(recordHash);
    const anchorReceipt = await anchorTx.wait();
    line("tx hash", anchorReceipt.hash);
    line("block", anchorReceipt.blockNumber);
    line("gas used", anchorReceipt.gasUsed.toString());
  } else {
    line("status", "already anchored in a previous run");
  }

  // -- 4. Verify -------------------------------------------------------------
  console.log("\n=== 4. ANYONE VERIFIES IT (no account, no gas) ===================\n");
  const result = await registry.verify(recordHash);
  line("exists", result.exists);
  line("issuer on chain", result.issuerName);
  line("issuer active", result.issuerActive);
  line("anchored at", new Date(Number(result.issuedAt) * 1000).toISOString());
  line("revoked", result.revoked);

  // -- 5. Tamper -------------------------------------------------------------
  console.log("\n=== 5. THE FORGERY TEST ==========================================\n");
  console.log("  Someone edits the CGPA from 3.21 to 3.91 and presents it:\n");

  const forged = JSON.parse(JSON.stringify(credential));
  forged.academic.cgpa = "3.91";
  const forgedCanonical = `VERIDOCK-RECORD-V1\n${JSON.stringify(forged)}`;
  const forgedHash = ethers.keccak256(ethers.toUtf8Bytes(forgedCanonical));

  line("forged CGPA", forged.academic.cgpa);
  line("forged hash", forgedHash);

  const forgedResult = await registry.verify(forgedHash);
  line("exists on ledger", forgedResult.exists);

  console.log("");
  if (result.exists && !forgedResult.exists && recordHash !== forgedHash) {
    console.log("  PASS — the genuine record verifies; a single altered character");
    console.log("         produces a hash the ledger has never seen.\n");
  } else {
    throw new Error("Tamper-evidence check failed — this must never happen.");
  }

  console.log("=== SUMMARY ======================================================\n");
  line("total anchors", (await registry.anchorCount()).toString());
  line("total issuers", (await registry.issuerCount()).toString());
  line("final block", await ethers.provider.getBlockNumber());
  console.log("");
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
