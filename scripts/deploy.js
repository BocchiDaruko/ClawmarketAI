const { ethers } = require("hardhat");

async function main() {
  const [deployer] = await ethers.getSigners();
  console.log("Deploying contracts with:", deployer.address);
  console.log("Balance:", ethers.formatEther(await ethers.provider.getBalance(deployer.address)), "ETH");

  // 1. Deploy Marketplace
  const Marketplace = await ethers.getContractFactory("Marketplace");
  const marketplace = await Marketplace.deploy();
  await marketplace.waitForDeployment();
  console.log("Marketplace deployed to:", await marketplace.getAddress());

  // 2. Deploy SmartWallet
  const SmartWallet = await ethers.getContractFactory("SmartWallet");
  const wallet = await SmartWallet.deploy();
  await wallet.waitForDeployment();
  console.log("SmartWallet deployed to:", await wallet.getAddress());

  // 3. Deploy Escrow
  const Escrow = await ethers.getContractFactory("Escrow");
  const escrow = await Escrow.deploy();
  await escrow.waitForDeployment();
  console.log("Escrow deployed to:", await escrow.getAddress());

  // 4. Deploy ReputationScore (linked to Marketplace)
  const ReputationScore = await ethers.getContractFactory("ReputationScore");
  const reputation = await ReputationScore.deploy(await marketplace.getAddress());
  await reputation.waitForDeployment();
  console.log("ReputationScore deployed to:", await reputation.getAddress());

  console.log("\n✅ All contracts deployed. Update your .env:");
  console.log(`MARKETPLACE_ADDRESS=${await marketplace.getAddress()}`);
  console.log(`SMART_WALLET_ADDRESS=${await wallet.getAddress()}`);
  console.log(`ESCROW_ADDRESS=${await escrow.getAddress()}`);
  console.log(`REPUTATION_ADDRESS=${await reputation.getAddress()}`);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
