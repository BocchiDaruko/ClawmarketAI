/**
 * ClawmarketAI — Deploy Script
 * scripts/deploy.js
 *
 * Deploys in order (dependency chain):
 *   1. ReputationScore
 *   2. Escrow
 *   3. Marketplace  (needs Escrow + Reputation)
 *   4. SmartWallet  (one per agent owner — deploy separately)
 *
 * Usage:
 *   npx hardhat run scripts/deploy.js --network baseSepolia
 *   npx hardhat run scripts/deploy.js --network base
 */

const { ethers } = require("hardhat");
const fs         = require("fs");
const path       = require("path");

// ── Base Mainnet token addresses ──────────────────────────────────────────────
const USDC_BASE  = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913";

// ── Deployment config ─────────────────────────────────────────────────────────
const CONFIG = {
  // Your deployer / admin address
  admin: process.env.ADMIN_ADDRESS,

  // Fee wallet (receives protocol fees)
  feeWallet: process.env.FEE_WALLET,

  // CLAW and CLAWX token addresses (deploy or use existing)
  clawToken:  process.env.CLAW_TOKEN_ADDRESS,
  clawxToken: process.env.CLAWX_TOKEN_ADDRESS,

  // BuyAndBurn contract address (deploy separately or use a simple burner)
  buyAndBurn: process.env.BUY_AND_BURN_ADDRESS,

  // Multisig config for SmartWallet (example: 2-of-3)
  signers:  (process.env.MULTISIG_SIGNERS || "").split(",").filter(Boolean),
  required: parseInt(process.env.MULTISIG_REQUIRED || "2"),
  multisigThresholdUsdc: ethers.parseUnits(
    process.env.MULTISIG_THRESHOLD_USDC || "500", 6
  ), // 500 USDC → requires multisig

  // Initial daily limit for each agent (USDC, 6 decimals)
  agentDailyLimitUsdc: ethers.parseUnits(
    process.env.AGENT_DAILY_LIMIT || "200", 6
  ),
};

async function main() {
  const [deployer] = await ethers.getSigners();
  console.log("\n=== ClawmarketAI Deployment ===");
  console.log(`Network:  ${(await ethers.provider.getNetwork()).name}`);
  console.log(`Deployer: ${deployer.address}`);
  console.log(`Balance:  ${ethers.formatEther(await ethers.provider.getBalance(deployer.address))} ETH\n`);

  // Validate config
  const admin = CONFIG.admin || deployer.address;
  const feeWallet = CONFIG.feeWallet || deployer.address;
  if (!CONFIG.clawToken || !CONFIG.clawxToken) {
    throw new Error("CLAW_TOKEN_ADDRESS and CLAWX_TOKEN_ADDRESS must be set");
  }

  // ── 1. ReputationScore ──────────────────────────────────────────────────────
  console.log("Deploying ReputationScore...");
  const ReputationScore = await ethers.getContractFactory("ReputationScore");
  const reputation = await ReputationScore.deploy(admin);
  await reputation.waitForDeployment();
  console.log(`  ReputationScore: ${await reputation.getAddress()}`);

  // ── 2. Escrow ───────────────────────────────────────────────────────────────
  console.log("Deploying Escrow...");
  const Escrow = await ethers.getContractFactory("Escrow");
  const escrow = await Escrow.deploy(admin, feeWallet);
  await escrow.waitForDeployment();
  console.log(`  Escrow:          ${await escrow.getAddress()}`);

  // ── 3. Marketplace ──────────────────────────────────────────────────────────
  console.log("Deploying Marketplace...");
  const Marketplace = await ethers.getContractFactory("Marketplace");
  const marketplace = await Marketplace.deploy(
    admin,
    USDC_BASE,
    CONFIG.clawToken,
    CONFIG.clawxToken,
    feeWallet,
    CONFIG.buyAndBurn || feeWallet,   // fallback to feeWallet if no buyAndBurn
    await escrow.getAddress(),
    await reputation.getAddress(),
  );
  await marketplace.waitForDeployment();
  console.log(`  Marketplace:     ${await marketplace.getAddress()}`);

  // ── 4. Grant roles ──────────────────────────────────────────────────────────
  console.log("\nGranting roles...");

  const MARKETPLACE_ROLE = ethers.keccak256(ethers.toUtf8Bytes("MARKETPLACE_ROLE"));
  const UPDATER_ROLE     = ethers.keccak256(ethers.toUtf8Bytes("UPDATER_ROLE"));

  // Marketplace can call Escrow.lock()
  await escrow.grantRole(MARKETPLACE_ROLE, await marketplace.getAddress());
  console.log("  Escrow.MARKETPLACE_ROLE → Marketplace ✓");

  // Marketplace can update ReputationScore
  await reputation.grantRole(UPDATER_ROLE, await marketplace.getAddress());
  console.log("  ReputationScore.UPDATER_ROLE → Marketplace ✓");

  // Escrow can update ReputationScore (for dispute resolution)
  await reputation.grantRole(UPDATER_ROLE, await escrow.getAddress());
  console.log("  ReputationScore.UPDATER_ROLE → Escrow ✓");

  // ── 5. SmartWallet (example — one per agent owner) ──────────────────────────
  console.log("\nDeploying example SmartWallet...");
  const SmartWallet = await ethers.getContractFactory("SmartWallet");
  const signers     = CONFIG.signers.length >= CONFIG.required
    ? CONFIG.signers
    : [deployer.address];   // fallback: deployer is the only signer

  const wallet = await SmartWallet.deploy(
    admin,                           // owner
    signers,                         // multisig signers
    Math.min(CONFIG.required, signers.length),
    CONFIG.multisigThresholdUsdc,    // threshold in USDC (6 dec)
  );
  await wallet.waitForDeployment();
  console.log(`  SmartWallet:     ${await wallet.getAddress()}`);

  // ── 6. Save addresses ───────────────────────────────────────────────────────
  const chainId = (await ethers.provider.getNetwork()).chainId;
  const output  = {
    network:          chainId.toString(),
    deployedAt:       new Date().toISOString(),
    deployer:         deployer.address,
    ReputationScore:  await reputation.getAddress(),
    Escrow:           await escrow.getAddress(),
    Marketplace:      await marketplace.getAddress(),
    SmartWallet:      await wallet.getAddress(),
    tokens: {
      USDC:  USDC_BASE,
      CLAW:  CONFIG.clawToken,
      CLAWX: CONFIG.clawxToken,
    },
  };

  const outPath = path.join(__dirname, `../deployments/${chainId}.json`);
  fs.mkdirSync(path.dirname(outPath), { recursive: true });
  fs.writeFileSync(outPath, JSON.stringify(output, null, 2));

  console.log(`\n=== Deployment complete ===`);
  console.log(`Addresses saved to: deployments/${chainId}.json`);
  console.log(JSON.stringify(output, null, 2));
}

main().catch((err) => {
  console.error(err);
  process.exitCode = 1;
});
