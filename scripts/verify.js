// scripts/verify.js
// ─────────────────────────────────────────────────────────────────────────────
//  ClawmarketAI — Contract Verification Script
//  Reads deployments/<network>.json and verifies all contracts on Basescan.
//
//  Usage:
//    npx hardhat run scripts/verify.js --network baseSepolia
//    npx hardhat run scripts/verify.js --network base
// ─────────────────────────────────────────────────────────────────────────────

const hre    = require("hardhat");
const ethers = hre.ethers;
const fs     = require("fs");
const path   = require("path");

async function verify(contractAddress, constructorArgs, contractName) {
  console.log(`\n  Verifying ${contractName} at ${contractAddress}...`);
  try {
    await hre.run("verify:verify", {
      address:              contractAddress,
      constructorArguments: constructorArgs,
    });
    console.log(`  ✅ ${contractName} verified`);
  } catch (err) {
    if (err.message.includes("Already Verified") || err.message.includes("already verified")) {
      console.log(`  ✓  ${contractName} already verified`);
    } else {
      console.warn(`  ⚠️  ${contractName} verification failed: ${err.message}`);
    }
  }
}

async function main() {
  const network = hre.network.name;
  const deploymentsFile = path.join(__dirname, `../deployments/${network}.json`);

  if (!fs.existsSync(deploymentsFile)) {
    throw new Error(
      `No deployment found for network "${network}".\n` +
      `Run deploy first: npx hardhat run scripts/deploy.js --network ${network}`
    );
  }

  const d = JSON.parse(fs.readFileSync(deploymentsFile, "utf8"));

  console.log(`\n🦀 ClawmarketAI — Verifying contracts on ${network}`);
  console.log(`   Deployed at: ${d.deployedAt}`);

  // ReputationScore(address admin)
  await verify(
    d.contracts.ReputationScore,
    [d.config.admin],
    "ReputationScore"
  );

  // Escrow(address admin, address feeWallet)
  await verify(
    d.contracts.Escrow,
    [d.config.admin, d.config.feeWallet],
    "Escrow"
  );

  // Marketplace(admin, usdc, claw, clawx, feeWallet, buyAndBurn, escrow, reputation)
  await verify(
    d.contracts.Marketplace,
    [
      d.config.admin,
      d.tokens.USDC,
      d.tokens.CLAW,
      d.tokens.CLAWX,
      d.config.feeWallet,
      d.config.buyAndBurn,
      d.contracts.Escrow,
      d.contracts.ReputationScore,
    ],
    "Marketplace"
  );

  // SmartWallet(owner, signers[], requiredSignatures, multisigThreshold)
  await verify(
    d.contracts.SmartWallet,
    [
      d.config.admin,
      [d.config.admin],
      1,
      ethers.parseUnits("1000", 6).toString(),
    ],
    "SmartWallet"
  );

  console.log(`\n${"═".repeat(60)}`);
  console.log(`  ✅ Verification complete — ${network}`);
  console.log(`  View on Basescan:`);
  const explorerBase = network === "base"
    ? "https://basescan.org/address/"
    : "https://sepolia.basescan.org/address/";
  console.log(`  Marketplace     : ${explorerBase}${d.contracts.Marketplace}`);
  console.log(`  Escrow          : ${explorerBase}${d.contracts.Escrow}`);
  console.log(`  ReputationScore : ${explorerBase}${d.contracts.ReputationScore}`);
  console.log(`  SmartWallet     : ${explorerBase}${d.contracts.SmartWallet}`);
  console.log(`${"═".repeat(60)}\n`);
}

main().catch((err) => {
  console.error(err);
  process.exitCode = 1;
});
