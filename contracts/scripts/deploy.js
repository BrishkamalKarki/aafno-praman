/**
 * Deploy CredentialRegistry and publish the artifacts the backend needs.
 *
 * Writes `deployments/<network>.json` containing the address, ABI and the
 * deploying block. The backend reads that file (or the equivalent env vars) so
 * nobody has to copy a hex address between terminals during a demo — the most
 * reliable way to break a live walkthrough.
 */
const fs = require("node:fs");
const path = require("node:path");
const hre = require("hardhat");

async function main() {
  const [deployer] = await hre.ethers.getSigners();
  const network = hre.network.name;

  const balance = await hre.ethers.provider.getBalance(deployer.address);
  console.log(`network   : ${network}`);
  console.log(`deployer  : ${deployer.address}`);
  console.log(`balance   : ${hre.ethers.formatEther(balance)} ETH`);

  if (balance === 0n) {
    throw new Error(
      `Deployer ${deployer.address} has no balance on ${network}. ` +
        "Fund it before deploying."
    );
  }

  // The deployer becomes the initial registrar — the platform root of trust.
  // In production this is a multisig; for the demo it is account #0.
  const registrar = process.env.REGISTRAR_ADDRESS || deployer.address;

  const factory = await hre.ethers.getContractFactory("CredentialRegistry");
  const registry = await factory.deploy(registrar);
  await registry.waitForDeployment();

  const address = await registry.getAddress();
  const receipt = await registry.deploymentTransaction().wait();

  console.log(`registrar : ${registrar}`);
  console.log(`registry  : ${address}`);
  console.log(`block     : ${receipt.blockNumber}`);

  const artifact = await hre.artifacts.readArtifact("CredentialRegistry");
  const outDir = path.join(__dirname, "..", "deployments");
  fs.mkdirSync(outDir, { recursive: true });

  const deployment = {
    network,
    chainId: Number((await hre.ethers.provider.getNetwork()).chainId),
    address,
    registrar,
    deployedAtBlock: receipt.blockNumber,
    deployedAt: new Date().toISOString(),
    abi: artifact.abi,
  };

  const outFile = path.join(outDir, `${network}.json`);
  fs.writeFileSync(outFile, `${JSON.stringify(deployment, null, 2)}\n`);
  console.log(`written   : ${path.relative(process.cwd(), outFile)}`);

  // Also drop the ABI where the backend expects it, so a fresh clone needs no
  // manual wiring between the contracts and backend workspaces.
  const backendAbiDir = path.join(
    __dirname,
    "..",
    "..",
    "backend",
    "apps",
    "ledger",
    "abi"
  );
  if (fs.existsSync(path.join(backendAbiDir, ".."))) {
    fs.mkdirSync(backendAbiDir, { recursive: true });
    fs.writeFileSync(
      path.join(backendAbiDir, "CredentialRegistry.json"),
      `${JSON.stringify({ abi: artifact.abi }, null, 2)}\n`
    );
    console.log("written   : backend/apps/ledger/abi/CredentialRegistry.json");
  }

  console.log("\nExport these for the backend:");
  console.log(`  CHAIN_CONTRACT_ADDRESS=${address}`);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
