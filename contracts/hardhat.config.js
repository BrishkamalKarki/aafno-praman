require("@nomicfoundation/hardhat-ethers");
require("@nomicfoundation/hardhat-chai-matchers");
require("@nomicfoundation/hardhat-network-helpers");
require("solidity-coverage");

/**
 * Hardhat configuration.
 *
 * The local node stays available for tests and offline work: deterministic
 * accounts, instant blocks, zero cost. `sepolia` is the public target — the
 * same deploy script and the same backend reach it by changing env vars only.
 *
 * Sepolia rather than a Polygon testnet because the credential fingerprints are
 * anchored as Ethereum calldata and Sepolia is the network wallets ship with
 * enabled by default. A verifier checking a graduate's degree can paste the
 * transaction hash into sepolia.etherscan.io without first being told to add a
 * custom network, which is the entire point of anchoring somewhere public.
 *
 * Plugins are required individually rather than via hardhat-toolbox: the
 * toolbox drags in TypeChain and hardhat-verify, neither of which a JavaScript
 * project deploying to a local node has any use for.
 */

const MNEMONIC =
  process.env.HARDHAT_MNEMONIC ||
  "test test test test test test test test test test test junk";

module.exports = {
  solidity: {
    version: "0.8.24",
    settings: {
      optimizer: { enabled: true, runs: 200 },
    },
  },
  networks: {
    hardhat: {
      chainId: 31337,
      accounts: { mnemonic: MNEMONIC, count: 20 },
    },
    localhost: {
      url: process.env.CHAIN_RPC_URL || "http://127.0.0.1:8545",
      chainId: 31337,
      accounts: { mnemonic: MNEMONIC, count: 20 },
    },
    sepolia: {
      // Default is a public no-key endpoint so `deploy:sepolia` works without
      // an Infura or Alchemy account. Set SEPOLIA_RPC_URL to a dedicated
      // provider before anything resembling production traffic — the public
      // ones rate-limit, and a rate-limited deploy fails halfway.
      url:
        process.env.SEPOLIA_RPC_URL ||
        "https://ethereum-sepolia-rpc.publicnode.com",
      chainId: 11155111,
      accounts: process.env.DEPLOYER_PRIVATE_KEY
        ? [process.env.DEPLOYER_PRIVATE_KEY]
        : [],
    },
  },
  paths: {
    sources: "./contracts",
    tests: "./test",
    artifacts: "./artifacts",
  },
  mocha: { timeout: 60000 },
};
