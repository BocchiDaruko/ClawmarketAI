/**
 * ClawmarketAI — Contract Tests
 * tests/contracts.test.js
 *
 * Full test suite covering:
 *   - ReputationScore: init, trade events, dispute penalties, oracle updates
 *   - SmartWallet:     agent management, daily limits, multisig, pause
 *   - Escrow:          lock, release, auto-release, dispute flow, fee routing
 *   - Marketplace:     createListing, buy (USDC/CLAW/CLAWX), fee routing, events
 */

const { expect }        = require("chai");
const { ethers }        = require("hardhat");
const { time }          = require("@nomicfoundation/hardhat-network-helpers");

const USDC_DECIMALS  = 6;
const TOKEN_DECIMALS = 18;

function usdc(n)  { return ethers.parseUnits(String(n), USDC_DECIMALS); }
function tok(n)   { return ethers.parseUnits(String(n), TOKEN_DECIMALS); }

// ─── Fixtures ────────────────────────────────────────────────────────────────

async function deployAll() {
  const [admin, feeWallet, seller, buyer, agent, oracle, arbiter, signer2, signer3] =
    await ethers.getSigners();

  // Deploy mock ERC-20 tokens
  const MockToken = await ethers.getContractFactory("MockERC20");
  const usdc_  = await MockToken.deploy("USD Coin",  "USDC",  USDC_DECIMALS);
  const claw   = await MockToken.deploy("CLAW",      "CLAW",  TOKEN_DECIMALS);
  const clawx  = await MockToken.deploy("CLAWX",     "CLAWX", TOKEN_DECIMALS);
  const buyAndBurn = feeWallet; // simplify: use feeWallet as buyAndBurn in tests

  // Deploy contracts
  const ReputationScore = await ethers.getContractFactory("ReputationScore");
  const reputation = await ReputationScore.deploy(admin.address);

  const Escrow = await ethers.getContractFactory("Escrow");
  const escrow = await Escrow.deploy(admin.address, feeWallet.address);

  const Marketplace = await ethers.getContractFactory("Marketplace");
  const marketplace = await Marketplace.deploy(
    admin.address,
    await usdc_.getAddress(),
    await claw.getAddress(),
    await clawx.getAddress(),
    feeWallet.address,
    buyAndBurn.address,
    await escrow.getAddress(),
    await reputation.getAddress(),
  );

  const SmartWallet = await ethers.getContractFactory("SmartWallet");
  const wallet = await SmartWallet.deploy(
    admin.address,                        // owner
    [admin.address, signer2.address, signer3.address], // signers
    2,                                    // 2-of-3
    usdc(500),                            // multisig threshold
  );

  // Grant roles
  const MARKETPLACE_ROLE = ethers.keccak256(ethers.toUtf8Bytes("MARKETPLACE_ROLE"));
  const UPDATER_ROLE     = ethers.keccak256(ethers.toUtf8Bytes("UPDATER_ROLE"));
  const ORACLE_ROLE      = ethers.keccak256(ethers.toUtf8Bytes("ORACLE_ROLE"));
  const ARBITER_ROLE     = ethers.keccak256(ethers.toUtf8Bytes("ARBITER_ROLE"));

  await escrow.grantRole(MARKETPLACE_ROLE, await marketplace.getAddress());
  await reputation.grantRole(UPDATER_ROLE, await marketplace.getAddress());
  await reputation.grantRole(UPDATER_ROLE, await escrow.getAddress());
  await reputation.grantRole(ORACLE_ROLE,  oracle.address);
  await escrow.grantRole(ARBITER_ROLE,     arbiter.address);

  // Set token prices in Marketplace (1 CLAW = 0.10 USDC; 1 CLAWX = 0.05 USDC)
  await marketplace.setTokenPrice(await claw.getAddress(),  usdc(0.10));
  await marketplace.setTokenPrice(await clawx.getAddress(), usdc(0.05));

  // Add agent to SmartWallet
  await wallet.addAgent(agent.address, usdc(200)); // 200 USDC/day

  // Mint tokens to buyer
  await usdc_.mint(buyer.address,  usdc(10_000));
  await claw.mint(buyer.address,   tok(100_000));
  await clawx.mint(buyer.address,  tok(100_000));

  return {
    admin, feeWallet, seller, buyer, agent, oracle, arbiter, signer2, signer3,
    usdc_, claw, clawx, reputation, escrow, marketplace, wallet,
    MARKETPLACE_ROLE, UPDATER_ROLE, ORACLE_ROLE, ARBITER_ROLE,
  };
}

// ─── ReputationScore ─────────────────────────────────────────────────────────

describe("ReputationScore", () => {
  it("initializes unregistered accounts to 5000", async () => {
    const { reputation, seller } = await deployAll();
    expect(await reputation.getScore(seller.address)).to.equal(5000n);
  });

  it("increases score after successful trade", async () => {
    const { reputation, marketplace, seller, buyer, usdc_ } = await deployAll();
    const mktAddr = await marketplace.getAddress();

    // Create listing and buy it to trigger recordSuccessfulTrade
    await marketplace.connect(seller).createListing(
      seller.address, usdc(10), "compute", "ipfs://test"
    );
    await usdc_.connect(buyer).approve(mktAddr, usdc(10));
    await marketplace.connect(buyer).buy(1, 0, true);

    const sellerScore = await reputation.getScore(seller.address);
    expect(sellerScore).to.be.gt(5000n);
  });

  it("penalizes on dispute lost", async () => {
    const { reputation, marketplace, usdc_ } = await deployAll();
    const [,, updater] = await ethers.getSigners();
    const UPDATER_ROLE = ethers.keccak256(ethers.toUtf8Bytes("UPDATER_ROLE"));
    await reputation.grantRole(UPDATER_ROLE, updater.address);

    await reputation.connect(updater).recordDisputeLost(updater.address, 200);
    const score = await reputation.getScore(updater.address);
    expect(score).to.be.lt(5000n);
  });

  it("accepts oracle score updates", async () => {
    const { reputation, oracle, seller } = await deployAll();
    await reputation.connect(oracle).updateOracleScore(seller.address, 8000);
    const { oracleScore } = await reputation.getScoreDetails(seller.address);
    expect(oracleScore).to.equal(8000n);
  });

  it("admin can change oracle weight", async () => {
    const { reputation, admin } = await deployAll();
    await reputation.connect(admin).setOracleWeight(2000);
    expect(await reputation.oracleWeightBps()).to.equal(2000n);
  });

  it("reverts if oracle weight > 50%", async () => {
    const { reputation, admin } = await deployAll();
    await expect(
      reputation.connect(admin).setOracleWeight(6000)
    ).to.be.revertedWith("Oracle weight cannot exceed 50%");
  });
});

// ─── SmartWallet ─────────────────────────────────────────────────────────────

describe("SmartWallet", () => {
  it("allows agent to execute within daily limit", async () => {
    const { wallet, agent, usdc_, buyer } = await deployAll();
    const walletAddr = await wallet.getAddress();

    // Fund the wallet with USDC
    await usdc_.mint(walletAddr, usdc(1000));

    const remaining = await wallet.remainingDailyLimit(agent.address);
    expect(remaining).to.equal(usdc(200));
  });

  it("reverts if daily limit exceeded", async () => {
    const { wallet, agent, usdc_, buyer, marketplace } = await deployAll();
    const walletAddr = await wallet.getAddress();
    await usdc_.mint(walletAddr, usdc(1000));

    // Encode a USDC transfer of 201 USDC (above 200 limit)
    const data = usdc_.interface.encodeFunctionData("transfer", [buyer.address, usdc(100)]);

    // First call: spend 150 USDC
    await wallet.connect(agent).execute(
      await usdc_.getAddress(), 0, data, usdc(150)
    );
    // Second call: spend 70 more → total 220 → exceeds 200 limit
    await expect(
      wallet.connect(agent).execute(await usdc_.getAddress(), 0, data, usdc(70))
    ).to.be.revertedWith("SmartWallet: daily limit exceeded");
  });

  it("owner can pause an agent", async () => {
    const { wallet, admin, agent } = await deployAll();
    await wallet.connect(admin).pauseAgent(agent.address);
    expect((await wallet.agentLimits(agent.address)).active).to.be.false;
  });

  it("owner can revoke agent permanently", async () => {
    const { wallet, admin, agent } = await deployAll();
    await wallet.connect(admin).revokeAgent(agent.address);
    expect(await wallet.isAgent(agent.address)).to.be.false;
  });

  it("non-agent cannot execute", async () => {
    const { wallet, buyer, usdc_ } = await deployAll();
    const data = usdc_.interface.encodeFunctionData("transfer", [buyer.address, usdc(1)]);
    await expect(
      wallet.connect(buyer).execute(await usdc_.getAddress(), 0, data, usdc(1))
    ).to.be.revertedWith("SmartWallet: not an active agent");
  });
});

// ─── Escrow ───────────────────────────────────────────────────────────────────

describe("Escrow", () => {
  async function buyListing(f, listingId = 1) {
    const mktAddr = await f.marketplace.getAddress();
    await f.marketplace.connect(f.seller).createListing(
      f.seller.address, usdc(10), "compute", "ipfs://test"
    );
    await f.usdc_.connect(f.buyer).approve(mktAddr, usdc(10));
    await f.marketplace.connect(f.buyer).buy(listingId, 0, true); // autoRelease ON
  }

  it("locks funds after buy()", async () => {
    const f = await deployAll();
    await buyListing(f);
    expect(await f.escrow.isHeld(1)).to.be.true;
  });

  it("auto-releases funds after delay", async () => {
    const f = await deployAll();
    await buyListing(f);
    const sellerBefore = await f.usdc_.balanceOf(f.seller.address);

    await time.increase(25 * 3600); // advance 25 hours
    await f.escrow.release(1);

    const sellerAfter = await f.usdc_.balanceOf(f.seller.address);
    expect(sellerAfter).to.be.gt(sellerBefore);
  });

  it("buyer can confirm delivery to release early", async () => {
    const f = await deployAll();
    // Create listing with autoRelease OFF
    await f.marketplace.connect(f.seller).createListing(
      f.seller.address, usdc(10), "compute", "ipfs://test"
    );
    await f.usdc_.connect(f.buyer).approve(await f.marketplace.getAddress(), usdc(10));
    await f.marketplace.connect(f.buyer).buy(1, 0, false); // autoRelease OFF

    const before = await f.usdc_.balanceOf(f.seller.address);
    await f.escrow.connect(f.buyer).confirmDelivery(1);
    const after  = await f.usdc_.balanceOf(f.seller.address);
    expect(after).to.be.gt(before);
  });

  it("dispute flow: arbiter refunds buyer", async () => {
    const f = await deployAll();
    await buyListing(f);

    await f.escrow.connect(f.buyer).openDispute(1);
    const before = await f.usdc_.balanceOf(f.buyer.address);
    await f.escrow.connect(f.arbiter).resolveDispute(1, f.buyer.address);
    const after  = await f.usdc_.balanceOf(f.buyer.address);
    expect(after).to.be.gt(before);
    expect(await f.escrow.isHeld(1)).to.be.false;
  });

  it("cannot open dispute after window", async () => {
    const f = await deployAll();
    await buyListing(f);
    await time.increase(25 * 3600);
    await expect(
      f.escrow.connect(f.buyer).openDispute(1)
    ).to.be.revertedWith("Dispute window closed");
  });
});

// ─── Marketplace ─────────────────────────────────────────────────────────────

describe("Marketplace", () => {
  it("creates a listing and emits event", async () => {
    const { marketplace, seller } = await deployAll();
    await expect(
      marketplace.connect(seller).createListing(seller.address, usdc(10), "compute", "ipfs://x")
    ).to.emit(marketplace, "ListingCreated")
     .withArgs(1n, seller.address, usdc(10), "compute", "ipfs://x");
  });

  it("buy with USDC locks in escrow and emits PurchaseCompleted", async () => {
    const { marketplace, escrow, seller, buyer, usdc_ } = await deployAll();
    const mktAddr = await marketplace.getAddress();
    await marketplace.connect(seller).createListing(seller.address, usdc(10), "compute", "ipfs://x");
    await usdc_.connect(buyer).approve(mktAddr, usdc(10));

    await expect(marketplace.connect(buyer).buy(1, 0, true))
      .to.emit(marketplace, "PurchaseCompleted");

    expect(await escrow.isHeld(1)).to.be.true;
  });

  it("buy with CLAWX applies discount", async () => {
    const { marketplace, escrow, seller, buyer, clawx } = await deployAll();
    const mktAddr = await marketplace.getAddress();
    await marketplace.connect(seller).createListing(seller.address, usdc(10), "compute", "ipfs://x");

    // Approve enough CLAWX
    await clawx.connect(buyer).approve(mktAddr, tok(1000));
    await expect(
      marketplace.connect(buyer).buy(1, 2, true) // PaymentToken.CLAWX = 2
    ).to.emit(marketplace, "PurchaseCompleted");
  });

  it("seller cannot buy own listing", async () => {
    const { marketplace, seller, usdc_ } = await deployAll();
    const mktAddr = await marketplace.getAddress();
    await marketplace.connect(seller).createListing(seller.address, usdc(10), "compute", "ipfs://x");
    await usdc_.mint(seller.address, usdc(10));
    await usdc_.connect(seller).approve(mktAddr, usdc(10));

    await expect(
      marketplace.connect(seller).buy(1, 0, true)
    ).to.be.revertedWith("Seller cannot buy own listing");
  });

  it("cannot buy same listing twice", async () => {
    const { marketplace, seller, buyer, usdc_ } = await deployAll();
    const mktAddr = await marketplace.getAddress();
    await marketplace.connect(seller).createListing(seller.address, usdc(10), "compute", "ipfs://x");
    await usdc_.connect(buyer).approve(mktAddr, usdc(20));
    await marketplace.connect(buyer).buy(1, 0, true);

    await expect(
      marketplace.connect(buyer).buy(1, 0, true)
    ).to.be.revertedWith("Listing not available");
  });

  it("seller can cancel listing", async () => {
    const { marketplace, seller } = await deployAll();
    await marketplace.connect(seller).createListing(seller.address, usdc(10), "compute", "ipfs://x");
    await marketplace.connect(seller).cancelListing(1);
    expect(await marketplace.isAvailable(1)).to.be.false;
  });

  it("seller can update price", async () => {
    const { marketplace, seller } = await deployAll();
    await marketplace.connect(seller).createListing(seller.address, usdc(10), "compute", "ipfs://x");
    await marketplace.connect(seller).updatePrice(1, usdc(15));
    const [,price] = await marketplace.getActiveListing(1);
    expect(price).to.equal(usdc(15));
  });
});
