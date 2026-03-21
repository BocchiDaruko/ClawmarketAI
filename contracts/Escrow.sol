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
 *         Flow:
 *           1. Marketplace calls lock()     — buyer funds held in escrow.
 *           2. After delivery:
 *              a. Seller calls release()    — or auto-release fires after window.
 *              b. Buyer calls confirmDelivery() to release early.
 *           3. If disputed:
 *              a. Buyer calls openDispute() within disputeWindow.
 *              b. ARBITER_ROLE resolves → resolveDispute(winner).
 *
 *         Auto-release is ON by default; buyer can disable it per trade.
 *         Supports USDC, $CLAW, $CLAWX, and ETH.
 */
contract Escrow is AccessControl, ReentrancyGuard, Pausable {
    using SafeERC20 for IERC20;

    // ─── Roles ────────────────────────────────────────────────────────────────
    bytes32 public constant ADMIN_ROLE     = keccak256("ADMIN_ROLE");
    bytes32 public constant MARKETPLACE_ROLE = keccak256("MARKETPLACE_ROLE");
    bytes32 public constant ARBITER_ROLE   = keccak256("ARBITER_ROLE");

    // ─── Structs ──────────────────────────────────────────────────────────────
    enum EscrowStatus { Locked, Released, Refunded, Disputed, Resolved }

    struct EscrowRecord {
        address buyer;
        address seller;
        address token;          // address(0) = ETH
        uint256 amount;
        uint256 lockedAt;
        uint256 releaseAfter;   // auto-release timestamp
        bool    autoRelease;    // buyer can disable auto-release
        bool    buyerConfirmed; // buyer explicitly confirmed delivery
        EscrowStatus status;
    }

    // listingId → EscrowRecord
    mapping(uint256 => EscrowRecord) public escrows;

    // ─── Config ───────────────────────────────────────────────────────────────
    uint256 public disputeWindow    = 24 hours;   // buyer can dispute within this window
    uint256 public autoReleaseDelay = 24 hours;   // auto-release after this delay post-lock

    // Protocol fee (basis points, e.g. 100 = 1%)
    uint256 public feeBps    = 100;
    address public feeWallet;

    // ─── Events ───────────────────────────────────────────────────────────────
    event Locked(uint256 indexed listingId, address buyer, address seller,
                 address token, uint256 amount, bool autoRelease);
    event Released(uint256 indexed listingId, address seller, uint256 net, uint256 fee);
    event Refunded(uint256 indexed listingId, address buyer, uint256 amount);
    event DeliveryConfirmed(uint256 indexed listingId, address buyer);
    event DisputeOpened(uint256 indexed listingId, address buyer);
    event DisputeResolved(uint256 indexed listingId, address winner, uint256 amount);
    event AutoReleaseToggled(uint256 indexed listingId, bool enabled);
    event FeeUpdated(uint256 newBps);
    event DisputeWindowUpdated(uint256 newWindow);
    event AutoReleaseDelayUpdated(uint256 newDelay);

    // ─── Constructor ──────────────────────────────────────────────────────────
    constructor(address admin, address _feeWallet) {
        require(admin != address(0) && _feeWallet != address(0), "Invalid addresses");
        _grantRole(DEFAULT_ADMIN_ROLE, admin);
        _grantRole(ADMIN_ROLE,         admin);
        feeWallet = _feeWallet;
    }

    // ─── Core: Lock ───────────────────────────────────────────────────────────

    /**
     * @notice Lock funds for a trade. Called by Marketplace.sol after buy().
     * @param listingId   Unique listing identifier.
     * @param buyer       Buyer wallet address.
     * @param seller      Seller wallet address.
     * @param token       ERC-20 token address (address(0) = ETH).
     * @param amount      Amount to lock (token decimals).
     * @param autoRelease Whether to auto-release after delay (buyer's choice).
     */
    function lock(
        uint256 listingId,
        address buyer,
        address seller,
        address token,
        uint256 amount,
        bool    autoRelease
    ) external payable onlyRole(MARKETPLACE_ROLE) whenNotPaused nonReentrant {
        require(escrows[listingId].buyer == address(0), "Escrow already exists");
        require(buyer != address(0) && seller != address(0), "Invalid parties");
        require(amount > 0, "Amount must be > 0");

        if (token == address(0)) {
            require(msg.value == amount, "ETH amount mismatch");
        } else {
            IERC20(token).safeTransferFrom(buyer, address(this), amount);
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

    // ─── Core: Release ────────────────────────────────────────────────────────

    /**
     * @notice Release funds to seller. Can be called by:
     *           - The seller at any time after disputeWindow closes (no dispute opened).
     *           - Anyone if autoRelease is on and releaseAfter has passed.
     */
    function release(uint256 listingId) external nonReentrant whenNotPaused {
        EscrowRecord storage e = escrows[listingId];
        require(e.status == EscrowStatus.Locked, "Escrow not locked");
        require(e.buyer != address(0),            "Escrow does not exist");

        bool disputeWindowPassed = block.timestamp > e.lockedAt + disputeWindow;
        bool autoReleaseReady    = e.autoRelease && block.timestamp >= e.releaseAfter;
        bool sellerClaiming      = msg.sender == e.seller && disputeWindowPassed;
        bool buyerConfirmed      = e.buyerConfirmed;

        require(
            autoReleaseReady || sellerClaiming || buyerConfirmed,
            "Escrow: release conditions not met"
        );

        e.status = EscrowStatus.Released;
        _transferToSeller(listingId, e);
    }

    /**
     * @notice Buyer explicitly confirms delivery, releasing funds immediately.
     */
    function confirmDelivery(uint256 listingId) external nonReentrant whenNotPaused {
        EscrowRecord storage e = escrows[listingId];
        require(e.status == EscrowStatus.Locked, "Escrow not locked");
        require(msg.sender == e.buyer,            "Only buyer can confirm");

        e.buyerConfirmed = true;
        e.status         = EscrowStatus.Released;
        emit DeliveryConfirmed(listingId, msg.sender);
        _transferToSeller(listingId, e);
    }

    /**
     * @notice Buyer toggles auto-release on/off (only while escrow is Locked).
     */
    function toggleAutoRelease(uint256 listingId, bool enabled) external {
        EscrowRecord storage e = escrows[listingId];
        require(e.status == EscrowStatus.Locked, "Escrow not locked");
        require(msg.sender == e.buyer,            "Only buyer can toggle");
        e.autoRelease = enabled;
        emit AutoReleaseToggled(listingId, enabled);
    }

    // ─── Dispute flow ─────────────────────────────────────────────────────────

    /**
     * @notice Buyer opens a dispute. Must be within disputeWindow.
     */
    function openDispute(uint256 listingId) external whenNotPaused {
        EscrowRecord storage e = escrows[listingId];
        require(e.status == EscrowStatus.Locked,                   "Escrow not locked");
        require(msg.sender == e.buyer,                             "Only buyer can dispute");
        require(block.timestamp <= e.lockedAt + disputeWindow,     "Dispute window closed");

        e.status = EscrowStatus.Disputed;
        emit DisputeOpened(listingId, msg.sender);
    }

    /**
     * @notice Arbiter resolves a dispute.
     * @param listingId Escrow to resolve.
     * @param winner    address(buyer) = full refund, address(seller) = full release.
     *                  Any other address = split (50/50 minus fee).
     */
    function resolveDispute(
        uint256 listingId,
        address winner
    ) external onlyRole(ARBITER_ROLE) nonReentrant {
        EscrowRecord storage e = escrows[listingId];
        require(e.status == EscrowStatus.Disputed, "No open dispute");

        e.status = EscrowStatus.Resolved;

        if (winner == e.buyer) {
            // Full refund to buyer
            _transfer(e.token, e.buyer, e.amount);
            emit Refunded(listingId, e.buyer, e.amount);
        } else if (winner == e.seller) {
            // Full release to seller (minus fee)
            _transferToSeller(listingId, e);
        } else {
            // Split 50/50 (minus fee on each half)
            uint256 half    = e.amount / 2;
            uint256 feeEach = (half * feeBps) / 10_000;
            _transfer(e.token, e.buyer,   half - feeEach);
            _transfer(e.token, e.seller,  half - feeEach);
            _transfer(e.token, feeWallet, feeEach * 2);
        }

        emit DisputeResolved(listingId, winner, e.amount);
    }

    // ─── View helpers ─────────────────────────────────────────────────────────

    function isHeld(uint256 listingId) external view returns (bool) {
        return escrows[listingId].status == EscrowStatus.Locked
            || escrows[listingId].status == EscrowStatus.Disputed;
    }

    function getEscrow(uint256 listingId) external view returns (EscrowRecord memory) {
        return escrows[listingId];
    }

    // ─── Admin ────────────────────────────────────────────────────────────────

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

    // ─── Internal ─────────────────────────────────────────────────────────────

    function _transferToSeller(uint256 listingId, EscrowRecord storage e) internal {
        uint256 fee    = (e.amount * feeBps) / 10_000;
        uint256 net    = e.amount - fee;
        _transfer(e.token, e.seller,    net);
        _transfer(e.token, feeWallet,   fee);
        emit Released(listingId, e.seller, net, fee);
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
}
