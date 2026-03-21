// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "@openzeppelin/contracts/access/AccessControl.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import "@openzeppelin/contracts/utils/Pausable.sol";
import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";

/**
 * @title  Escrow
 * @author ClawmarketAI
 * @notice Trustless escrow for ClawmarketAI trades on Base.
 *
 *  FIXES APPLIED:
 *   [1] lock() pulls funds from msg.sender (Marketplace), not from buyer.
 *       Marketplace already holds the funds after buy() — buyer has 0 balance here.
 *   [2] Double-fee removed. Escrow.feeBps defaults to 0. Marketplace handles all
 *       protocol fees before calling lock(). Escrow only moves net amounts.
 *       feeBps is kept configurable (admin) for future standalone use, but ships as 0.
 *   [3] resolveDispute() restricts winner to buyer or seller only.
 *       Split resolution is buyer+seller 50/50 — no third-party address risk.
 *   [4] Re-lock guard: listingId cannot be reused if a record already exists
 *       (regardless of status).
 *
 *  Flow:
 *    1. Marketplace calls lock()          — net funds (post-fee) held in escrow.
 *    2. After delivery:
 *       a. Buyer calls confirmDelivery()  — immediate release to seller.
 *       b. Auto-release fires after delay (if buyer enabled it).
 *       c. Seller calls release()         — after disputeWindow closes.
 *    3. If disputed:
 *       a. Buyer calls openDispute()      — within disputeWindow.
 *       b. ARBITER_ROLE resolves          — resolveDispute(winner).
 *
 *  Supported tokens: USDC, $CLAW, $CLAWX (and ETH for future use).
 */
contract Escrow is AccessControl, ReentrancyGuard, Pausable {
    using SafeERC20 for IERC20;

    // ─────────────────────────────────────────────────────────────────────────
    //  ROLES
    // ─────────────────────────────────────────────────────────────────────────

    bytes32 public constant ADMIN_ROLE       = keccak256("ADMIN_ROLE");
    bytes32 public constant MARKETPLACE_ROLE = keccak256("MARKETPLACE_ROLE");
    bytes32 public constant ARBITER_ROLE     = keccak256("ARBITER_ROLE");

    // ─────────────────────────────────────────────────────────────────────────
    //  TYPES
    // ─────────────────────────────────────────────────────────────────────────

    enum EscrowStatus { Locked, Released, Refunded, Disputed, Resolved }

    struct EscrowRecord {
        address buyer;
        address seller;
        address token;           // address(0) = ETH
        uint256 amount;          // net amount (fees already deducted by Marketplace)
        uint256 lockedAt;
        uint256 releaseAfter;    // auto-release timestamp
        bool    autoRelease;     // buyer can toggle off
        bool    buyerConfirmed;  // buyer explicitly confirmed delivery
        EscrowStatus status;
    }

    // listingId → EscrowRecord
    mapping(uint256 => EscrowRecord) public escrows;

    // ─────────────────────────────────────────────────────────────────────────
    //  CONFIG
    // ─────────────────────────────────────────────────────────────────────────

    uint256 public disputeWindow    = 24 hours;
    uint256 public autoReleaseDelay = 24 hours;

    /// @dev [FIX-2] Ships as 0 — Marketplace handles all protocol fees.
    ///      Can be set > 0 only if Escrow is used standalone in the future.
    uint256 public feeBps    = 0;
    address public feeWallet;

    // ─────────────────────────────────────────────────────────────────────────
    //  EVENTS
    // ─────────────────────────────────────────────────────────────────────────

    event Locked(
        uint256 indexed listingId,
        address buyer,
        address seller,
        address token,
        uint256 amount,
        bool    autoRelease
    );
    event Released(uint256 indexed listingId, address seller, uint256 amount);
    event Refunded(uint256 indexed listingId, address buyer,  uint256 amount);
    event DeliveryConfirmed(uint256 indexed listingId, address buyer);
    event DisputeOpened(uint256 indexed listingId, address buyer);
    event DisputeResolved(uint256 indexed listingId, address winner, uint256 amount);
    event AutoReleaseToggled(uint256 indexed listingId, bool enabled);
    event FeeUpdated(uint256 newBps);
    event DisputeWindowUpdated(uint256 newWindow);
    event AutoReleaseDelayUpdated(uint256 newDelay);

    // ─────────────────────────────────────────────────────────────────────────
    //  CONSTRUCTOR
    // ─────────────────────────────────────────────────────────────────────────

    constructor(address admin, address _feeWallet) {
        require(admin      != address(0), "Invalid admin");
        require(_feeWallet != address(0), "Invalid feeWallet");
        _grantRole(DEFAULT_ADMIN_ROLE, admin);
        _grantRole(ADMIN_ROLE,         admin);
        feeWallet = _feeWallet;
    }

    // ─────────────────────────────────────────────────────────────────────────
    //  LOCK
    // ─────────────────────────────────────────────────────────────────────────

    /**
     * @notice Lock net funds for a trade. Called exclusively by Marketplace.
     * @dev    [FIX-1] Funds are pulled from msg.sender (Marketplace), not from buyer.
     *         Marketplace already transferred funds from buyer and holds them.
     *         [FIX-4] Reverts if listingId already has any record (prevents re-lock).
     *
     * @param listingId   Unique listing ID (from Marketplace).
     * @param buyer       Buyer wallet address.
     * @param seller      Seller wallet address.
     * @param token       ERC-20 address (address(0) = ETH).
     * @param amount      Net amount to lock (fees already removed by Marketplace).
     * @param autoRelease Whether to auto-release after autoReleaseDelay.
     */
    function lock(
        uint256 listingId,
        address buyer,
        address seller,
        address token,
        uint256 amount,
        bool    autoRelease
    ) external payable onlyRole(MARKETPLACE_ROLE) whenNotPaused nonReentrant {
        // [FIX-4] Prevent re-lock on any existing record
        require(escrows[listingId].lockedAt == 0, "Escrow already exists");
        require(buyer  != address(0), "Invalid buyer");
        require(seller != address(0), "Invalid seller");
        require(amount > 0,           "Amount must be > 0");

        // [FIX-1] Pull from Marketplace (msg.sender), not from buyer
        if (token == address(0)) {
            require(msg.value == amount, "ETH amount mismatch");
        } else {
            IERC20(token).safeTransferFrom(msg.sender, address(this), amount);
        }

        escrows[listingId] = EscrowRecord({
            buyer:          buyer,
            seller:         seller,
            token:          token,
            amount:         amount,
            lockedAt:       block.timestamp,
            releaseAfter:   block.timestamp + autoReleaseDelay,
            autoRelease:    autoRelease,
            buyerConfirmed: false,
            status:         EscrowStatus.Locked
        });

        emit Locked(listingId, buyer, seller, token, amount, autoRelease);
    }

    // ─────────────────────────────────────────────────────────────────────────
    //  RELEASE
    // ─────────────────────────────────────────────────────────────────────────

    /**
     * @notice Release funds to seller. Callable when:
     *           - autoRelease is on AND releaseAfter has passed, OR
     *           - seller calls after disputeWindow closes, OR
     *           - buyer already confirmed delivery.
     */
    function release(uint256 listingId) external nonReentrant whenNotPaused {
        EscrowRecord storage e = escrows[listingId];
        require(e.status == EscrowStatus.Locked, "Escrow not locked");
        require(e.lockedAt > 0,                  "Escrow does not exist");

        bool autoReleaseReady  = e.autoRelease && block.timestamp >= e.releaseAfter;
        bool disputeWindowDone = block.timestamp > e.lockedAt + disputeWindow;
        bool sellerClaiming    = msg.sender == e.seller && disputeWindowDone;
        bool buyerConfirmed    = e.buyerConfirmed;

        require(
            autoReleaseReady || sellerClaiming || buyerConfirmed,
            "Release conditions not met"
        );

        e.status = EscrowStatus.Released;
        _sendToSeller(listingId, e);
    }

    /**
     * @notice Buyer confirms delivery — releases funds to seller immediately.
     */
    function confirmDelivery(uint256 listingId) external nonReentrant whenNotPaused {
        EscrowRecord storage e = escrows[listingId];
        require(e.status == EscrowStatus.Locked, "Escrow not locked");
        require(msg.sender == e.buyer,           "Only buyer can confirm");

        e.buyerConfirmed = true;
        e.status         = EscrowStatus.Released;
        emit DeliveryConfirmed(listingId, msg.sender);
        _sendToSeller(listingId, e);
    }

    /**
     * @notice Buyer toggles auto-release (only while Locked).
     */
    function toggleAutoRelease(uint256 listingId, bool enabled) external {
        EscrowRecord storage e = escrows[listingId];
        require(e.status == EscrowStatus.Locked, "Escrow not locked");
        require(msg.sender == e.buyer,           "Only buyer can toggle");
        e.autoRelease = enabled;
        emit AutoReleaseToggled(listingId, enabled);
    }

    // ─────────────────────────────────────────────────────────────────────────
    //  DISPUTE FLOW
    // ─────────────────────────────────────────────────────────────────────────

    /**
     * @notice Buyer opens a dispute within the disputeWindow.
     */
    function openDispute(uint256 listingId) external whenNotPaused {
        EscrowRecord storage e = escrows[listingId];
        require(e.status == EscrowStatus.Locked,               "Escrow not locked");
        require(msg.sender == e.buyer,                         "Only buyer can dispute");
        require(block.timestamp <= e.lockedAt + disputeWindow, "Dispute window closed");

        e.status = EscrowStatus.Disputed;
        emit DisputeOpened(listingId, msg.sender);
    }

    /**
     * @notice Arbiter resolves a dispute.
     * @dev    [FIX-3] winner must be buyer or seller — no arbitrary address.
     *                  Split (neither wins fully) sends 50/50 to each party.
     *
     * @param listingId  Escrow to resolve.
     * @param winner     buyer address → full refund to buyer.
     *                   seller address → full release to seller.
     *                   address(0) → split 50/50 between buyer and seller.
     */
    function resolveDispute(
        uint256 listingId,
        address winner
    ) external onlyRole(ARBITER_ROLE) nonReentrant {
        EscrowRecord storage e = escrows[listingId];
        require(e.status == EscrowStatus.Disputed, "No open dispute");

        // [FIX-3] Only buyer, seller, or address(0) for split are valid
        require(
            winner == e.buyer || winner == e.seller || winner == address(0),
            "Invalid winner: must be buyer, seller, or address(0) for split"
        );

        e.status = EscrowStatus.Resolved;

        if (winner == e.buyer) {
            // Full refund to buyer
            _transfer(e.token, e.buyer, e.amount);
            emit Refunded(listingId, e.buyer, e.amount);

        } else if (winner == e.seller) {
            // Full release to seller
            _sendToSeller(listingId, e);

        } else {
            // Split 50/50 — address(0) means no clear winner
            uint256 half      = e.amount / 2;
            uint256 remainder = e.amount - (half * 2); // handle odd amounts
            _transfer(e.token, e.buyer,  half);
            _transfer(e.token, e.seller, half + remainder); // seller gets dust
            emit DisputeResolved(listingId, address(0), e.amount);
        }

        if (winner == e.buyer || winner == e.seller) {
            emit DisputeResolved(listingId, winner, e.amount);
        }
    }

    // ─────────────────────────────────────────────────────────────────────────
    //  VIEW HELPERS
    // ─────────────────────────────────────────────────────────────────────────

    function isHeld(uint256 listingId) external view returns (bool) {
        EscrowStatus s = escrows[listingId].status;
        return s == EscrowStatus.Locked || s == EscrowStatus.Disputed;
    }

    function getEscrow(uint256 listingId) external view returns (EscrowRecord memory) {
        return escrows[listingId];
    }

    function canAutoRelease(uint256 listingId) external view returns (bool) {
        EscrowRecord storage e = escrows[listingId];
        return e.status == EscrowStatus.Locked
            && e.autoRelease
            && block.timestamp >= e.releaseAfter;
    }

    // ─────────────────────────────────────────────────────────────────────────
    //  ADMIN
    // ─────────────────────────────────────────────────────────────────────────

    /// @dev [FIX-2] feeBps ships as 0. Only increase if Escrow is used standalone.
    function setFeeBps(uint256 newBps) external onlyRole(ADMIN_ROLE) {
        require(newBps <= 500, "Fee too high"); // max 5%
        feeBps = newBps;
        emit FeeUpdated(newBps);
    }

    function setDisputeWindow(uint256 newWindow) external onlyRole(ADMIN_ROLE) {
        require(newWindow >= 1 hours && newWindow <= 7 days, "Invalid window");
        disputeWindow = newWindow;
        emit DisputeWindowUpdated(newWindow);
    }

    function setAutoReleaseDelay(uint256 newDelay) external onlyRole(ADMIN_ROLE) {
        require(newDelay >= 1 hours && newDelay <= 30 days, "Invalid delay");
        autoReleaseDelay = newDelay;
        emit AutoReleaseDelayUpdated(newDelay);
    }

    function setFeeWallet(address newWallet) external onlyRole(ADMIN_ROLE) {
        require(newWallet != address(0), "Invalid wallet");
        feeWallet = newWallet;
    }

    function pause()   external onlyRole(ADMIN_ROLE) { _pause(); }
    function unpause() external onlyRole(ADMIN_ROLE) { _unpause(); }

    // ─────────────────────────────────────────────────────────────────────────
    //  INTERNAL HELPERS
    // ─────────────────────────────────────────────────────────────────────────

    /**
     * @notice Send full escrow amount to seller.
     *         [FIX-2] No fee deducted here — Marketplace already handled it.
     *         feeBps is kept for future standalone use but is 0 by default.
     */
    function _sendToSeller(uint256 listingId, EscrowRecord storage e) internal {
        uint256 fee = (e.amount * feeBps) / 10_000; // 0 by default
        uint256 net = e.amount - fee;
        _transfer(e.token, e.seller, net);
        if (fee > 0) _transfer(e.token, feeWallet, fee);
        emit Released(listingId, e.seller, net);
    }

    function _transfer(address token, address to, uint256 amount) internal {
        if (amount == 0) return;
        if (token == address(0)) {
            (bool ok,) = to.call{value: amount}("");
            require(ok, "ETH transfer failed");
        } else {
            IERC20(token).safeTransfer(to, amount);
        }
    }

    // ─────────────────────────────────────────────────────────────────────────
    //  RECEIVE ETH
    // ─────────────────────────────────────────────────────────────────────────

    receive() external payable {}
}
