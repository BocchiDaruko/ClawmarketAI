const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("clawmarketAI Contracts", function () {

  let marketplace, wallet, escrow, reputation;
  let owner, buyer, seller, agent;

  beforeEach(async function () {
    [owner, buyer, seller, agent] = await ethers.getSigners();

    const Marketplace = await ethers.getContractFactory("Marketplace");
    marketplace = await Marketplace.deploy();

    const SmartWallet = await ethers.getContractFactory("SmartWallet");
    wallet = await SmartWallet.deploy();

    const Escrow = await ethers.getContractFactory("Escrow");
    escrow = await Escrow.deploy();

    const ReputationScore = await ethers.getContractFactory("ReputationScore");
    reputation = await ReputationScore.deploy(await marketplace.getAddress());
  });

  // ── Marketplace ─────────────────────────────────────────────────────────
  describe("Marketplace", function () {
    it("allows a seller to create a listing", async function () {
      await expect(
        marketplace.connect(seller).list("compute", "ipfs://test", ethers.parseEther("0.1"))
      ).to.emit(marketplace, "Listed");
    });

    it("allows a buyer to purchase a listing", async function () {
      await marketplace.connect(seller).list("compute", "ipfs://test", ethers.parseEther("0.1"));
      await expect(
        marketplace.connect(buyer).purchase(1, { value: ethers.parseEther("0.1") })
      ).to.emit(marketplace, "Purchased");
    });

    it("prevents a seller from buying their own listing", async function () {
      await marketplace.connect(seller).list("data", "ipfs://test2", ethers.parseEther("0.05"));
      await expect(
        marketplace.connect(seller).purchase(1, { value: ethers.parseEther("0.05") })
      ).to.be.revertedWith("Cannot buy own listing");
    });

    it("allows delisting by the seller", async function () {
      await marketplace.connect(seller).list("api-access", "ipfs://test3", ethers.parseEther("0.2"));
      await expect(
        marketplace.connect(seller).delist(1)
      ).to.emit(marketplace, "Delisted");
    });
  });

  // ── SmartWallet ──────────────────────────────────────────────────────────
  describe("SmartWallet", function () {
    it("owner can authorize an agent with a spend limit", async function () {
      await expect(
        wallet.connect(owner).authorizeAgent(agent.address, ethers.parseEther("1"))
      ).to.emit(wallet, "AgentAuthorized");
    });

    it("unauthorized agent cannot execute", async function () {
      await expect(
        wallet.connect(agent).execute(seller.address, 0, "0x")
      ).to.be.revertedWith("Not authorized agent");
    });

    it("owner can revoke an agent", async function () {
      await wallet.connect(owner).authorizeAgent(agent.address, ethers.parseEther("1"));
      await expect(
        wallet.connect(owner).revokeAgent(agent.address)
      ).to.emit(wallet, "AgentRevoked");
    });
  });

  // ── Escrow ───────────────────────────────────────────────────────────────
  describe("Escrow", function () {
    it("buyer can create a deal with locked funds", async function () {
      await expect(
        escrow.connect(buyer).createDeal(seller.address, { value: ethers.parseEther("0.1") })
      ).to.emit(escrow, "DealCreated");
    });

    it("buyer can confirm delivery and release funds", async function () {
      await escrow.connect(buyer).createDeal(seller.address, { value: ethers.parseEther("0.1") });
      await expect(
        escrow.connect(buyer).confirmDelivery(1)
      ).to.emit(escrow, "DealConfirmed");
    });

    it("buyer can raise a dispute", async function () {
      await escrow.connect(buyer).createDeal(seller.address, { value: ethers.parseEther("0.1") });
      await expect(
        escrow.connect(buyer).dispute(1)
      ).to.emit(escrow, "DealDisputed");
    });
  });

  // ── ReputationScore ──────────────────────────────────────────────────────
  describe("ReputationScore", function () {
    it("records a successful trade and updates score", async function () {
      await reputation.connect(owner).recordTrade(agent.address, true, 5);
      const score = await reputation.getScore(agent.address);
      expect(score.totalTrades).to.equal(1n);
      expect(score.successfulTrades).to.equal(1n);
    });

    it("correctly calculates average rating", async function () {
      await reputation.connect(owner).recordTrade(agent.address, true, 4);
      await reputation.connect(owner).recordTrade(agent.address, true, 5);
      const avg = await reputation.getAverageRating(agent.address);
      expect(avg).to.equal(450n); // (4+5)/2 * 100 = 450
    });

    it("returns isTrusted correctly", async function () {
      await reputation.connect(owner).recordTrade(agent.address, true, 5);
      expect(await reputation.isTrusted(agent.address, 1, 400)).to.be.true;
      expect(await reputation.isTrusted(agent.address, 10, 400)).to.be.false;
    });
  });
});
