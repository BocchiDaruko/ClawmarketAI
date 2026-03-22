// scripts/deploy.js
// ─────────────────────────────────────────────────────────────────────────────
//  ClawmarketAI — Full Deploy Script
//  Deploys all 4 contracts in the correct order and wires up roles.
//
//  Usage:
//    Base Sepolia (testnet):  npx hardhat run scripts/deploy.js --network baseSepolia
//    Base Mainnet:            npx hardhat run scripts/deploy.js --network base
//
//  After deploy, run verification:
//    npx hardhat run scripts/verify.js --network baseSepolia
// ─────────────────────────────────────────────────────────────────────────────

const hre     = require("hardhat");
const ethers  = hre.ethers;
const fs      = require("fs");
const path    = require("path");

// ─── Config ───────────────────────────────────────────────────────────────────

const CONFIG = {
  // Token addresses — Base Mainnet
  mainnet: {
    usdc: "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
    claw:  process.env.CLAW_ADDRESS,
    clawx: process.env.CLAWX_ADDRESS,
  },
  // Token addresses — Base Sepolia (testnet mock addresses — deploy mocks first)
  testnet: {
    usdc:  process.env.TESTNET_USDC  || "0x0000000000000000000000000000000000000000",
    claw:  process.env.TESTNET_CLAW  || "0x0000000000000000000000000000000000000000",
    clawx: process.env.TESTNET_CLAWX || "0x0000000000000000000000000000000000000000",
  },
};

// ─── Helpers ──────────────────────────────────────────────────────────────────

function log(msg) {
  console.log(`\n${"─".repeat(60)}\n  ${msg}\n${"─".repeat(60)}`);
}

function addr(contract) {
  return contract.target ?? contract.address;
}

async function waitFor(tx) {
  const receipt = await tx.wait(2); // wait 2 confirmations
  return receipt;
}

// ─── Main ─────────────────────────────────────────────────────────────────────

async function main() {
  const network    = hre.network.name;
  const isMainnet  = network === "base";
  const isTestnet  = network === "baseSepolia";
  const isLocal    = network === "hardhat" || network === "localhost";

  console.log(`\n🦀 ClawmarketAI Deploy Script`);
  console.log(`   Network : ${network}`);
  console.log(`   Chain ID: ${hre.network.config.chainId}`);

  // ── Signers ──────────────────────────────────────────────────────────────────
  const [deployer] = await ethers.getSigners();
  const deployerAddress = await deployer.getAddress();

  const adminAddress    = process.env.ADMIN_ADDRESS    || deployerAddress;
  const feeWallet       = process.env.FEE_WALLET       || deployerAddress;
  const buyAndBurn      = process.env.BUY_AND_BURN_ADDRESS || feeWallet; // fallback to feeWallet

  console.log(`\n   Deployer : ${deployerAddress}`);
  console.log(`   Admin    : ${adminAddress}`);
  console.log(`   FeeWallet: ${feeWallet}`);
  console.log(`   BuyBurn  : ${buyAndBurn}`);

  const balance = await ethers.provider.getBalance(deployerAddress);
  console.log(`   ETH Balance: ${ethers.formatEther(balance)} ETH`);

  if (balance === 0n) {
    throw new Error("Deployer has no ETH. Fund the wallet before deploying.");
  }

  // ── Token addresses ──────────────────────────────────────────────────────────
  let usdcAddress, clawAddress, clawxAddress;

  if (isMainnet) {
    usdcAddress  = CONFIG.mainnet.usdc;
    clawAddress  = CONFIG.mainnet.claw;
    clawxAddress = CONFIG.mainnet.clawx;

    if (!clawAddress || clawAddress === "0x") {
      throw new Error("CLAW_ADDRESS not set in .env — deploy $CLAW token first.");
    }
    if (!clawxAddress || clawxAddress === "0x") {
      throw new Error("CLAWX_ADDRESS not set in .env — deploy $CLAWX token first.");
    }
  } else {
    // Testnet / local — deploy mock ERC20s if addresses not set
    usdcAddress  = CONFIG.testnet.usdc;
    clawAddress  = CONFIG.testnet.claw;
    clawxAddress = CONFIG.testnet.clawx;

    const zeroAddr = "0x0000000000000000000000000000000000000000";
    if (
      usdcAddress  === zeroAddr ||
      clawAddress  === zeroAddr ||
      clawxAddress === zeroAddr
    ) {
      log("Deploying mock ERC20 tokens for testnet...");
      const MockERC20 = await ethers.getContractFactory("MockERC20");

      if (usdcAddress === zeroAddr) {
        const usdc = await MockERC20.deploy("USD Coin", "USDC", 6);
        await usdc.waitForDeployment();
        usdcAddress = addr(usdc);
        console.log(`   ✅ Mock USDC   : ${usdcAddress}`);
      }
      if (clawAddress === zeroAddr) {
        const claw = await MockERC20.deploy("Claw Token", "CLAW", 18);
        await claw.waitForDeployment();
        clawAddress = addr(claw);
        console.log(`   ✅ Mock CLAW   : ${clawAddress}`);
      }
      if (clawxAddress === zeroAddr) {
        const clawx = await MockERC20.deploy("ClawX Token", "CLAWX", 18);
        await clawx.waitForDeployment();
        clawxAddress = addr(clawx);
        console.log(`   ✅ Mock CLAWX  : ${clawxAddress}`);
      }
    }
  }

  console.log(`\n   USDC  : ${usdcAddress}`);
  console.log(`   CLAW  : ${clawAddress}`);
  console.log(`   CLAWX : ${clawxAddress}`);

  // ── 1. Deploy ReputationScore ─────────────────────────────────────────────────
  log("1/4  Deploying ReputationScore...");
  const ReputationScore = await ethers.getContractFactory("ReputationScore");
  const reputation = await ReputationScore.deploy(adminAddress);
  await reputation.waitForDeployment();
  const reputationAddress = addr(reputation);
  console.log(`   ✅ ReputationScore: ${reputationAddress}`);

  // ── 2. Deploy Escrow ──────────────────────────────────────────────────────────
  log("2/4  Deploying Escrow...");
  const Escrow = await ethers.getContractFactory("Escrow");
  const escrow = await Escrow.deploy(adminAddress, feeWallet);
  await escrow.waitForDeployment();
  const escrowAddress = addr(escrow);
  console.log(`   ✅ Escrow: ${escrowAddress}`);

  // ── 3. Deploy Marketplace ─────────────────────────────────────────────────────
  log("3/4  Deploying Marketplace...");
  const Marketplace = await ethers.getContractFactory("Marketplace");
  const marketplace = await Marketplace.deploy(
    adminAddress,
    usdcAddress,
    clawAddress,
    clawxAddress,
    feeWallet,
    buyAndBurn,
    escrowAddress,
    reputationAddress
  );
  await marketplace.waitForDeployment();
  const marketplaceAddress = addr(marketplace);
  console.log(`   ✅ Marketplace: ${marketplaceAddress}`);

  // ── 4. Deploy SmartWallet (factory pattern — deploy one reference wallet) ──────
  log("4/4  Deploying SmartWallet (reference instance)...");
  const SmartWallet = await ethers.getContractFactory("SmartWallet");
  const smartWallet = await SmartWallet.deploy(
    adminAddress,           // owner
    [adminAddress],         // signers (add more for production)
    1,                      // requiredSignatures (1-of-1 for testnet)
    ethers.parseUnits("1000", 6) // multisigThreshold: $1000 USDC
  );
  await smartWallet.waitForDeployment();
  const smartWalletAddress = addr(smartWallet);
  console.log(`   ✅ SmartWallet: ${smartWalletAddress}`);

  // ─── Wire up roles ─────────────────────────────────────────────────────────────
  log("Wiring up roles...");

  const MARKETPLACE_ROLE = ethers.keccak256(ethers.toUtf8Bytes("MARKETPLACE_ROLE"));
  const UPDATER_ROLE     = ethers.keccak256(ethers.toUtf8Bytes("UPDATER_ROLE"));
  const SELLER_ROLE      = ethers.keccak256(ethers.toUtf8Bytes("SELLER_ROLE"));

  // Marketplace gets MARKETPLACE_ROLE on Escrow
  // (allows Marketplace to call escrow.lock())
  let tx = await escrow.grantRole(MARKETPLACE_ROLE, marketplaceAddress);
  await waitFor(tx);
  console.log(`   ✅ Escrow.MARKETPLACE_ROLE → Marketplace`);

  // Marketplace gets UPDATER_ROLE on ReputationScore
  // (allows Marketplace to call reputation.recordSuccessfulTrade())
  tx = await reputation.grantRole(UPDATER_ROLE, marketplaceAddress);
  await waitFor(tx);
  console.log(`   ✅ ReputationScore.UPDATER_ROLE → Marketplace`);

  // Escrow gets UPDATER_ROLE on ReputationScore
  // (allows Escrow to call reputation.recordDisputeLost())
  tx = await reputation.grantRole(UPDATER_ROLE, escrowAddress);
  await waitFor(tx);
  console.log(`   ✅ ReputationScore.UPDATER_ROLE → Escrow`);

  // SmartWallet gets SELLER_ROLE on Marketplace
  // (allows SmartWallet agents to create listings on behalf of owners)
  tx = await marketplace.grantRole(SELLER_ROLE, smartWalletAddress);
  await waitFor(tx);
  console.log(`   ✅ Marketplace.SELLER_ROLE → SmartWallet`);

  // ─── Save deployment addresses ─────────────────────────────────────────────────
  log("Saving deployment addresses...");

  const deployment = {
    network:          network,
    chainId:          hre.network.config.chainId,
    deployedAt:       new Date().toISOString(),
    deployer:         deployerAddress,
    contracts: {
      ReputationScore: reputationAddress,
      Escrow:          escrowAddress,
      Marketplace:     marketplaceAddress,
      SmartWallet:     smartWalletAddress,
    },
    tokens: {
      USDC:  usdcAddress,
      CLAW:  clawAddress,
      CLAWX: clawxAddress,
    },
    config: {
      admin:       adminAddress,
      feeWallet:   feeWallet,
      buyAndBurn:  buyAndBurn,
    },
  };

  const deploymentsDir = path.join(__dirname, "../deployments");
  if (!fs.existsSync(deploymentsDir)) {
    fs.mkdirSync(deploymentsDir, { recursive: true });
  }

  const outFile = path.join(deploymentsDir, `${network}.json`);
  fs.writeFileSync(outFile, JSON.stringify(deployment, null, 2));
  console.log(`   ✅ Saved to deployments/${network}.json`);

  // ─── Summary ──────────────────────────────────────────────────────────────────
  console.log(`\n${"═".repeat(60)}`);
  console.log(`  🦀 ClawmarketAI Deploy Complete — ${network}`);
  console.log(`${"═".repeat(60)}`);
  console.log(`  ReputationScore : ${reputationAddress}`);
  console.log(`  Escrow          : ${escrowAddress}`);
  console.log(`  Marketplace     : ${marketplaceAddress}`);
  console.log(`  SmartWallet     : ${smartWalletAddress}`);
  console.log(`${"═".repeat(60)}`);
  console.log(`\n  Next step: verify contracts on Basescan`);
  console.log(`  Run: npx hardhat run scripts/verify.js --network ${network}\n`);
}

main().catch((err) => {
  console.error(err);
  process.exitCode = 1;
});
