const { expect } = require("chai");
const { ethers } = require("hardhat");
const { loadFixture, time } = require("@nomicfoundation/hardhat-network-helpers");

const KIND = { None: 0, Institution: 1, Employer: 2 };

/** keccak256 of an arbitrary label — stands in for a canonical record hash. */
const h = (label) => ethers.keccak256(ethers.toUtf8Bytes(label));

describe("CredentialRegistry", () => {
  async function deployFixture() {
    const [registrar, university, employer, outsider, newRegistrar] =
      await ethers.getSigners();

    const factory = await ethers.getContractFactory("CredentialRegistry");
    const registry = await factory.deploy(registrar.address);
    await registry.waitForDeployment();

    return { registry, registrar, university, employer, outsider, newRegistrar };
  }

  async function approvedFixture() {
    const ctx = await deployFixture();
    await ctx.registry
      .connect(ctx.registrar)
      .approveIssuer(ctx.university.address, KIND.Institution, "Tribhuvan University");
    await ctx.registry
      .connect(ctx.registrar)
      .approveIssuer(ctx.employer.address, KIND.Employer, "Leapfrog Technology");
    return ctx;
  }

  describe("deployment", () => {
    it("sets the initial registrar", async () => {
      const { registry, registrar } = await loadFixture(deployFixture);
      expect(await registry.registrar()).to.equal(registrar.address);
    });

    it("rejects the zero address as registrar", async () => {
      const factory = await ethers.getContractFactory("CredentialRegistry");
      await expect(factory.deploy(ethers.ZeroAddress)).to.be.revertedWithCustomError(
        factory,
        "ZeroAddress"
      );
    });

    it("starts with an empty registry", async () => {
      const { registry } = await loadFixture(deployFixture);
      expect(await registry.anchorCount()).to.equal(0);
      expect(await registry.issuerCount()).to.equal(0);
    });
  });

  describe("issuer onboarding (HR-01: root of trust)", () => {
    it("lets the registrar approve an institution", async () => {
      const { registry, registrar, university } = await loadFixture(deployFixture);

      await expect(
        registry
          .connect(registrar)
          .approveIssuer(university.address, KIND.Institution, "Kathmandu University")
      )
        .to.emit(registry, "IssuerApproved")
        .withArgs(university.address, KIND.Institution, "Kathmandu University", anyUint());

      const issuer = await registry.getIssuer(university.address);
      expect(issuer.kind).to.equal(KIND.Institution);
      expect(issuer.active).to.equal(true);
      expect(issuer.name).to.equal("Kathmandu University");
      expect(await registry.canAnchor(university.address)).to.equal(true);
    });

    it("blocks anyone but the registrar from approving issuers", async () => {
      const { registry, outsider, university } = await loadFixture(deployFixture);
      await expect(
        registry
          .connect(outsider)
          .approveIssuer(university.address, KIND.Institution, "Fake University")
      ).to.be.revertedWithCustomError(registry, "NotRegistrar");
    });

    it("rejects a nameless or None-kind issuer", async () => {
      const { registry, registrar, university } = await loadFixture(deployFixture);
      await expect(
        registry.connect(registrar).approveIssuer(university.address, KIND.Institution, "")
      ).to.be.revertedWithCustomError(registry, "EmptyName");
      await expect(
        registry.connect(registrar).approveIssuer(university.address, KIND.None, "X")
      ).to.be.revertedWithCustomError(registry, "InvalidIssuerKind");
    });

    it("refuses to approve the same issuer twice", async () => {
      const { registry, registrar, university } = await loadFixture(approvedFixture);
      await expect(
        registry.connect(registrar).approveIssuer(university.address, KIND.Institution, "Dup")
      ).to.be.revertedWithCustomError(registry, "IssuerAlreadyApproved");
    });
  });

  describe("anchoring (FR-03)", () => {
    it("anchors a record for an approved issuer", async () => {
      const { registry, university } = await loadFixture(approvedFixture);
      const hash = h("bsc-csit-2026-001");

      await expect(registry.connect(university).anchor(hash))
        .to.emit(registry, "RecordAnchored")
        .withArgs(hash, university.address, anyUint());

      const result = await registry.verify(hash);
      expect(result.exists).to.equal(true);
      expect(result.issuer).to.equal(university.address);
      expect(result.issuerName).to.equal("Tribhuvan University");
      expect(result.revoked).to.equal(false);
      expect(result.supersededBy).to.equal(ethers.ZeroHash);
      expect(await registry.anchorCount()).to.equal(1);
    });

    it("rejects an unapproved issuer (FR-06)", async () => {
      const { registry, outsider } = await loadFixture(approvedFixture);
      await expect(
        registry.connect(outsider).anchor(h("forged-degree"))
      ).to.be.revertedWithCustomError(registry, "IssuerNotApproved");
    });

    it("rejects the zero hash", async () => {
      const { registry, university } = await loadFixture(approvedFixture);
      await expect(
        registry.connect(university).anchor(ethers.ZeroHash)
      ).to.be.revertedWithCustomError(registry, "ZeroHash");
    });

    it("rejects a duplicate anchor (E-09 idempotency)", async () => {
      const { registry, university } = await loadFixture(approvedFixture);
      const hash = h("bsc-csit-2026-001");
      await registry.connect(university).anchor(hash);
      await expect(registry.connect(university).anchor(hash))
        .to.be.revertedWithCustomError(registry, "AlreadyAnchored")
        .withArgs(hash);
    });

    it("keeps issuers from anchoring another issuer's duplicate hash", async () => {
      const { registry, university, employer } = await loadFixture(approvedFixture);
      const hash = h("shared-hash");
      await registry.connect(university).anchor(hash);
      await expect(
        registry.connect(employer).anchor(hash)
      ).to.be.revertedWithCustomError(registry, "AlreadyAnchored");
    });

    it("returns exists=false for an unknown hash (E-12: no enumeration signal)", async () => {
      const { registry } = await loadFixture(approvedFixture);
      const result = await registry.verify(h("never-issued"));
      expect(result.exists).to.equal(false);
      expect(result.issuer).to.equal(ethers.ZeroAddress);
      expect(result.issuerName).to.equal("");
      expect(result.issuedAt).to.equal(0);
    });
  });

  describe("batch anchoring (FR-04)", () => {
    it("anchors a graduating batch in one transaction", async () => {
      const { registry, university } = await loadFixture(approvedFixture);
      const batch = Array.from({ length: 50 }, (_, i) => h(`grad-2026-${i}`));

      const tx = await registry.connect(university).anchorBatch(batch);
      await tx.wait();

      expect(await registry.anchorCount()).to.equal(50);
      for (const hash of batch) {
        expect(await registry.isAnchored(hash)).to.equal(true);
      }
    });

    it("is meaningfully cheaper per record than individual anchors", async () => {
      const { registry, university, employer } = await loadFixture(approvedFixture);

      const batch = Array.from({ length: 10 }, (_, i) => h(`batch-${i}`));
      const batchReceipt = await (
        await registry.connect(university).anchorBatch(batch)
      ).wait();

      let individualGas = 0n;
      for (let i = 0; i < 10; i++) {
        const receipt = await (
          await registry.connect(employer).anchor(h(`single-${i}`))
        ).wait();
        individualGas += receipt.gasUsed;
      }

      expect(batchReceipt.gasUsed).to.be.lessThan(individualGas);
    });

    it("rejects an empty batch", async () => {
      const { registry, university } = await loadFixture(approvedFixture);
      await expect(
        registry.connect(university).anchorBatch([])
      ).to.be.revertedWithCustomError(registry, "EmptyBatch");
    });

    it("rejects a batch over MAX_BATCH", async () => {
      const { registry, university } = await loadFixture(approvedFixture);
      const max = Number(await registry.MAX_BATCH());
      const batch = Array.from({ length: max + 1 }, (_, i) => h(`over-${i}`));
      await expect(registry.connect(university).anchorBatch(batch))
        .to.be.revertedWithCustomError(registry, "BatchTooLarge")
        .withArgs(max + 1, max);
    });

    it("reverts the whole batch when one hash is a duplicate (atomicity)", async () => {
      const { registry, university } = await loadFixture(approvedFixture);
      await registry.connect(university).anchor(h("existing"));

      await expect(
        registry
          .connect(university)
          .anchorBatch([h("fresh-a"), h("existing"), h("fresh-b")])
      ).to.be.revertedWithCustomError(registry, "AlreadyAnchored");

      // Nothing from the failed batch landed.
      expect(await registry.isAnchored(h("fresh-a"))).to.equal(false);
      expect(await registry.isAnchored(h("fresh-b"))).to.equal(false);
      expect(await registry.anchorCount()).to.equal(1);
    });
  });

  describe("revocation (HR-03)", () => {
    it("lets the issuing institution revoke with a reason", async () => {
      const { registry, university } = await loadFixture(approvedFixture);
      const hash = h("revoke-me");
      await registry.connect(university).anchor(hash);

      await expect(registry.connect(university).revoke(hash, "Degree rescinded: plagiarism"))
        .to.emit(registry, "RecordRevoked")
        .withArgs(hash, university.address, "Degree rescinded: plagiarism", anyUint());

      const result = await registry.verify(hash);
      expect(result.exists).to.equal(true); // history is preserved, not deleted
      expect(result.revoked).to.equal(true);
      expect(result.revocationReason).to.equal("Degree rescinded: plagiarism");
    });

    it("lets the registrar revoke when an issuer is defunct", async () => {
      const { registry, registrar, university } = await loadFixture(approvedFixture);
      const hash = h("registrar-revoke");
      await registry.connect(university).anchor(hash);

      await registry.connect(registrar).revoke(hash, "Issuer accreditation withdrawn");
      expect((await registry.verify(hash)).revoked).to.equal(true);
    });

    it("blocks a third party from revoking someone else's record", async () => {
      const { registry, university, employer } = await loadFixture(approvedFixture);
      const hash = h("not-yours");
      await registry.connect(university).anchor(hash);

      await expect(
        registry.connect(employer).revoke(hash, "malicious")
      ).to.be.revertedWithCustomError(registry, "NotRecordIssuer");
    });

    it("rejects revoking an unknown or already-revoked record, or an empty reason", async () => {
      const { registry, university } = await loadFixture(approvedFixture);
      const hash = h("double-revoke");

      await expect(
        registry.connect(university).revoke(h("ghost"), "reason")
      ).to.be.revertedWithCustomError(registry, "NotAnchored");

      await registry.connect(university).anchor(hash);
      await expect(
        registry.connect(university).revoke(hash, "")
      ).to.be.revertedWithCustomError(registry, "EmptyReason");

      await registry.connect(university).revoke(hash, "first");
      await expect(
        registry.connect(university).revoke(hash, "second")
      ).to.be.revertedWithCustomError(registry, "AlreadyRevoked");
    });

    it("still allows revocation after the issuer is suspended", async () => {
      // Suspension is exactly when fraudulent anchors need cleaning up.
      const { registry, registrar, university } = await loadFixture(approvedFixture);
      const hash = h("cleanup");
      await registry.connect(university).anchor(hash);
      await registry.connect(registrar).suspendIssuer(university.address, "Under investigation");

      await registry.connect(university).revoke(hash, "Issued in error");
      expect((await registry.verify(hash)).revoked).to.equal(true);
    });
  });

  describe("supersede (amendments)", () => {
    it("links the old anchor forward to the correction", async () => {
      const { registry, university } = await loadFixture(approvedFixture);
      const oldHash = h("name-misspelled");
      const newHash = h("name-corrected");
      await registry.connect(university).anchor(oldHash);

      await expect(registry.connect(university).supersede(oldHash, newHash))
        .to.emit(registry, "RecordSuperseded")
        .withArgs(oldHash, newHash, university.address, anyUint());

      // An already-printed QR for the old hash still resolves, and points forward.
      const old = await registry.verify(oldHash);
      expect(old.exists).to.equal(true);
      expect(old.supersededBy).to.equal(newHash);

      const current = await registry.verify(newHash);
      expect(current.exists).to.equal(true);
      expect(current.supersededBy).to.equal(ethers.ZeroHash);
    });

    it("refuses to supersede twice or to supersede another issuer's record", async () => {
      const { registry, university, employer } = await loadFixture(approvedFixture);
      const oldHash = h("v1");
      await registry.connect(university).anchor(oldHash);
      await registry.connect(university).supersede(oldHash, h("v2"));

      await expect(
        registry.connect(university).supersede(oldHash, h("v3"))
      ).to.be.revertedWithCustomError(registry, "AlreadySuperseded");

      const other = h("employer-record");
      await registry.connect(employer).anchor(other);
      await expect(
        registry.connect(university).supersede(other, h("hijack"))
      ).to.be.revertedWithCustomError(registry, "NotRecordIssuer");
    });
  });

  describe("suspension is not retroactive (E-02)", () => {
    it("keeps records anchored in good standing verifiable after suspension", async () => {
      const { registry, registrar, university } = await loadFixture(approvedFixture);
      const hash = h("graduated-before-suspension");
      await registry.connect(university).anchor(hash);
      const anchoredAt = (await registry.verify(hash)).issuedAt;

      await time.increase(3600);
      await registry
        .connect(registrar)
        .suspendIssuer(university.address, "Accreditation lapsed");

      const result = await registry.verify(hash);
      // The graduate's degree is untouched...
      expect(result.exists).to.equal(true);
      expect(result.revoked).to.equal(false);
      // ...but the verifier can see the issuer's current standing and when it changed.
      expect(result.issuerActive).to.equal(false);
      expect(result.issuerSuspendedAt).to.be.greaterThan(anchoredAt);
    });

    it("blocks new anchors while suspended and allows them again after reinstatement", async () => {
      const { registry, registrar, university } = await loadFixture(approvedFixture);
      await registry.connect(registrar).suspendIssuer(university.address, "Audit");

      expect(await registry.canAnchor(university.address)).to.equal(false);
      await expect(
        registry.connect(university).anchor(h("during-suspension"))
      ).to.be.revertedWithCustomError(registry, "IssuerSuspendedError");

      await registry.connect(registrar).reinstateIssuer(university.address);
      expect(await registry.canAnchor(university.address)).to.equal(true);
      await registry.connect(university).anchor(h("after-reinstatement"));
      expect(await registry.isAnchored(h("after-reinstatement"))).to.equal(true);
    });

    it("rejects suspending an unknown issuer, double suspension, or an empty reason", async () => {
      const { registry, registrar, university, outsider } = await loadFixture(approvedFixture);
      await expect(
        registry.connect(registrar).suspendIssuer(outsider.address, "reason")
      ).to.be.revertedWithCustomError(registry, "IssuerNotApproved");
      await expect(
        registry.connect(registrar).suspendIssuer(university.address, "")
      ).to.be.revertedWithCustomError(registry, "EmptyReason");

      await registry.connect(registrar).suspendIssuer(university.address, "once");
      await expect(
        registry.connect(registrar).suspendIssuer(university.address, "twice")
      ).to.be.revertedWithCustomError(registry, "IssuerSuspendedError");
    });
  });

  describe("registrar handover", () => {
    it("requires the incoming registrar to accept (no lockout)", async () => {
      const { registry, registrar, newRegistrar, university } =
        await loadFixture(deployFixture);

      await expect(registry.connect(registrar).transferRegistrar(newRegistrar.address))
        .to.emit(registry, "RegistrarTransferStarted")
        .withArgs(registrar.address, newRegistrar.address);

      // Still the old registrar until acceptance.
      expect(await registry.registrar()).to.equal(registrar.address);
      await expect(
        registry
          .connect(newRegistrar)
          .approveIssuer(university.address, KIND.Institution, "Too early")
      ).to.be.revertedWithCustomError(registry, "NotRegistrar");

      await expect(registry.connect(newRegistrar).acceptRegistrar())
        .to.emit(registry, "RegistrarTransferred")
        .withArgs(registrar.address, newRegistrar.address);

      expect(await registry.registrar()).to.equal(newRegistrar.address);
      await registry
        .connect(newRegistrar)
        .approveIssuer(university.address, KIND.Institution, "Now allowed");
    });

    it("lets only the pending registrar accept", async () => {
      const { registry, registrar, newRegistrar, outsider } = await loadFixture(deployFixture);
      await registry.connect(registrar).transferRegistrar(newRegistrar.address);
      await expect(
        registry.connect(outsider).acceptRegistrar()
      ).to.be.revertedWithCustomError(registry, "NotPendingRegistrar");
    });

    it("rejects a transfer to the zero address", async () => {
      const { registry, registrar } = await loadFixture(deployFixture);
      await expect(
        registry.connect(registrar).transferRegistrar(ethers.ZeroAddress)
      ).to.be.revertedWithCustomError(registry, "ZeroAddress");
    });
  });

  describe("tamper evidence (FR-12 / E-01)", () => {
    it("produces a different hash for a single altered character", async () => {
      const { registry, university } = await loadFixture(approvedFixture);

      // The exact demo moment: a CGPA nudged from 3.21 to 3.91.
      const honest = h('{"cgpa":"3.21","name":"Sita Sharma"}');
      const forged = h('{"cgpa":"3.91","name":"Sita Sharma"}');

      await registry.connect(university).anchor(honest);

      expect(honest).to.not.equal(forged);
      expect((await registry.verify(honest)).exists).to.equal(true);
      expect((await registry.verify(forged)).exists).to.equal(false);
    });
  });

  describe("enumeration helpers", () => {
    it("indexes anchors and issuers in insertion order", async () => {
      const { registry, university, employer } = await loadFixture(approvedFixture);
      await registry.connect(university).anchor(h("a"));
      await registry.connect(employer).anchor(h("b"));

      expect(await registry.anchorCount()).to.equal(2);
      expect(await registry.anchorAt(0)).to.equal(h("a"));
      expect(await registry.anchorAt(1)).to.equal(h("b"));

      expect(await registry.issuerCount()).to.equal(2);
      expect(await registry.issuerAt(0)).to.equal(university.address);
      expect(await registry.issuerAt(1)).to.equal(employer.address);
    });
  });
});

/** Matches any uint — used for block timestamps we do not control. */
function anyUint() {
  const { anyValue } = require("@nomicfoundation/hardhat-chai-matchers/withArgs");
  return anyValue;
}
