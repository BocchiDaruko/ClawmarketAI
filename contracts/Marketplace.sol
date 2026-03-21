// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "@openzeppelin/contracts/access/AccessControl.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import "@openzeppelin/contracts/utils/Pausable.sol";
import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";

import "./Escrow.sol";
import "./ReputationScore.sol";

/**
 * @title  Marketplace
 * @author ClawmarketAI
 * @notice Core marketplace for ClawmarketAI on Base (chain ID 8453).
 *
 *         Accepts three payment tokens:
 *           - USDC  : stable reference (6 decimals)
 *           - $CLAW : governance token — 50% of fees bought-back and burned
 *           - $CLAWX: utility token   — paying with CLAWX gives 20% fee discount
 *
 *         Flow:
 *           1. Seller calls createListing()
 *           2. Buyer calls buy()
 *              → funds sent to Escrow.lock()
 *              → PurchaseCompleted event emitted (agents listen here)
 *           3. Escrow releases to seller after delivery confirmation / auto-release
 *           4. ReputationScore updated for both parties
 *
 *         All fees in CLAW are routed to a BuyAndBurn contract (deflationary).
 *         All fees in CLAWX are sent to the fee wallet.
 *         All fees in USDC: 50% fee wallet, 50% CLAW buy-and-burn.
 */
contract Marketplace is AccessControl, ReentrancyGuard, Pausable {
    using SafeERC20 for IERC20;

    // ─── Roles ────────────────────────────────────────────────────────────────
    bytes32 public constant ADMIN_ROLE    = keccak256("ADMIN_ROLE");
    bytes32 public constant OPERATOR_ROLE = keccak256("OPERATOR_ROLE");

    // ─── Token addresses (Base Mainnet) ───────────────────────────────────────
    address public immutable USDC;   // 0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913
    address public immutable CLAW;
    address public immutable CLAWX;

    // ─── Fee config ───────────────────────────────────────────────────────────
    uint256 public feeBps         = 100;    // 1%  base fee
    uint256 public clawxDiscountBps = 200;  // 0.2% discount when paying with CLAWX (fee = 0.8%)
    address public feeWallet;
    address public buyAndBurnContract;

    // ─── External contracts ───────────────────────────────────────────────────
    Escrow          public escrow;
    ReputationScore public reputation;

    // ─── Listing storage ──────────────────────────────────────────────────────
    enum PaymentToken { USDC, CLAW, CLAWX }

    struct Listing {
        uint256  listingId;
        address  seller;
        uint256  priceUsdc;      // price in USDC (6 decimals) — reference price
        string   category;
        string   metadataUri;   // ipfs:// URI
        bool     available;
        uint256  createdAt;
        uint256  soldAt;
    }

    uint256 private _nextListingId = 1;
    mapping(uint256 => Listing) public listings;

    // seller → array of their listing IDs
    mapping(address => uint256[]) public sellerListings;

    // ─── Price feeds (for CLAW/CLAWX → USDC conversion) ─────────────────────
    // Simple oracle: admin sets exchange rates (production: use Chainlink)
    mapping(address => uint256) public tokenPriceUsdc; // token → price per 1e18 in USDC (6 dec)

    // ─── Events ───────────────────────────────────────────────────────────────
    event ListingCreated(
        uint256 indexed listingId,
        address indexed seller,
        uint256 priceUsdc,
        string  category,
        string  metadataUri
    );
    event ListingUpdated(uint256 indexed listingId, uint256 newPrice);
    event ListingCancelled(uint256 indexed listingId, address seller);
    event PurchaseCompleted(
        uint256 indexed listingId,
        address indexed buyer,
        address indexed seller,
        uint256 priceUsdc,
        address paymentToken,
        uint256 paymentAmount,
        uint256 fee
    );
    event FeeBurned(address token, uint256 amount);
    event TokenPriceSet(address token, uint256 priceUsdc);

    // ─── Constructor ──────────────────────────────────────────────────────────
    constructor(
        address admin,
        address _usdc,
        address _claw,
        address _clawx,
        address _feeWallet,
        address _buyAndBurn,
        address _escrow,
        address _reputation
    ) {
        require(admin != address(0), "Invalid admin");
        _grantRole(DEFAULT_ADMIN_ROLE, admin);
        _grantRole(ADMIN_ROLE,         admin);

        USDC              = _usdc;
        CLAW              = _claw;
        CLAWX             = _clawx;
        feeWallet         = _feeWallet;
        buyAndBurnContract = _buyAndBurn;
        escrow            = Escrow(payable(_escrow));
        reputation        = ReputationScore(_reputation);
    }

    // ─── Listing management ───────────────────────────────────────────────────

    /**
     * @notice Create a new listing. Called by Seller Agent via SmartWallet.
     * @param seller      Seller's wallet address.
     * @param priceUsdc   Price in USDC (6 decimals).
     * @param category    Good category (compute, data, ai-service, api-access…).
     * @param metadataUri IPFS URI with item metadata.
     * @return listingId  The assigned listing ID.
     */
    function createListing(
        address seller,
        uint256 priceUsdc,
        string calldata category,
        string calldata metadataUri
    ) external whenNotPaused returns (uint256 listingId) {
        require(seller != address(0),          "Invalid seller");
        require(priceUsdc > 0,                 "Price must be > 0");
        require(bytes(category).length > 0,    "Category required");
        require(bytes(metadataUri).length > 0, "MetadataUri required");

        listingId = _nextListingId++;
        listings[listingId] = Listing({
            listingId:   listingId,
            seller:      seller,
            priceUsdc:   priceUsdc,
            category:    category,
            metadataUri: metadataUri,
            available:   true,
            createdAt:   block.timestamp,
            soldAt:      0
        });
        sellerListings[seller].push(listingId);

        emit ListingCreated(listingId, seller, priceUsdc, category, metadataUri);
    }

    /**
     * @notice Update the price of an active listing. Seller only.
     */
    function updatePrice(uint256 listingId, uint256 newPriceUsdc) external whenNotPaused {
        Listing storage lst = listings[listingId];
        require(lst.available,          "Listing not available");
        require(lst.seller == msg.sender || hasRole(OPERATOR_ROLE, msg.sender),
                "Not seller");
        require(newPriceUsdc > 0, "Price must be > 0");
        lst.priceUsdc = newPriceUsdc;
        emit ListingUpdated(listingId, newPriceUsdc);
    }

    /**
     * @notice Cancel a listing. Seller or operator only.
     */
    function cancelListing(uint256 listingId) external whenNotPaused {
        Listing storage lst = listings[listingId];
        require(lst.available, "Already sold or cancelled");
        require(lst.seller == msg.sender || hasRole(OPERATOR_ROLE, msg.sender),
                "Not seller");
        lst.available = false;
        emit ListingCancelled(listingId, lst.seller);
    }

    // ─── Buy ──────────────────────────────────────────────────────────────────

    /**
     * @notice Purchase a listing.
     * @param listingId    The listing to buy.
     * @param paymentToken Which token to pay with (USDC / CLAW / CLAWX).
     * @param autoRelease  Whether escrow should auto-release after delay.
     *
     *        Price conversion:
     *          - USDC:  pay exactly priceUsdc.
     *          - CLAW:  pay priceUsdc worth of CLAW at current oracle rate.
     *          - CLAWX: same, but 0.2% fee discount applied.
     */
    function buy(
        uint256      listingId,
        PaymentToken paymentToken,
        bool         autoRelease
    ) external nonReentrant whenNotPaused {
        Listing storage lst = listings[listingId];
        require(lst.available,         "Listing not available");
        require(lst.seller != msg.sender, "Seller cannot buy own listing");

        lst.available = false;
        lst.soldAt    = block.timestamp;

        // ── Compute payment amount ────────────────────────────────────────────
        address token;
        uint256 paymentAmount;
        uint256 feeAmount;

        if (paymentToken == PaymentToken.USDC) {
            token         = USDC;
            paymentAmount = lst.priceUsdc;
            feeAmount     = (paymentAmount * feeBps) / 10_000;
        } else if (paymentToken == PaymentToken.CLAW) {
            token         = CLAW;
            paymentAmount = _toTokenAmount(CLAW, lst.priceUsdc);
            feeAmount     = (paymentAmount * feeBps) / 10_000;
        } else {
            // CLAWX — 0.2% discount
            token         = CLAWX;
            paymentAmount = _toTokenAmount(CLAWX, lst.priceUsdc);
            uint256 effectiveBps = feeBps > clawxDiscountBps
                ? feeBps - clawxDiscountBps
                : 0;
            feeAmount = (paymentAmount * effectiveBps) / 10_000;
        }

        // ── Transfer full amount from buyer to this contract first ────────────
        IERC20(token).safeTransferFrom(msg.sender, address(this), paymentAmount);

        // ── Route fee ─────────────────────────────────────────────────────────
        uint256 escrowAmount = paymentAmount - feeAmount;
        _routeFee(token, feeAmount);

        // ── Approve escrow to pull from this contract ─────────────────────────
        IERC20(token).approve(address(escrow), escrowAmount);

        // ── Lock in Escrow ────────────────────────────────────────────────────
        escrow.lock(
            listingId,
            msg.sender,      // buyer
            lst.seller,
            token,
            escrowAmount,
            autoRelease
        );

        // ── Update reputation ─────────────────────────────────────────────────
        try reputation.recordSuccessfulTrade(lst.seller, msg.sender) {} catch {}

        emit PurchaseCompleted(
            listingId,
            msg.sender,
            lst.seller,
            lst.priceUsdc,
            token,
            paymentAmount,
            feeAmount
        );
    }

    // ─── View helpers ─────────────────────────────────────────────────────────

    function isAvailable(uint256 listingId) external view returns (bool) {
        return listings[listingId].available;
    }

    function getActiveListing(uint256 listingId) external view returns (
        address seller,
        uint256 priceUsdc,
        string memory category,
        string memory metadataUri,
        bool    available
    ) {
        Listing storage lst = listings[listingId];
        return (lst.seller, lst.priceUsdc, lst.category, lst.metadataUri, lst.available);
    }

    function getSellerListings(address seller) external view returns (uint256[] memory) {
        return sellerListings[seller];
    }

    /**
     * @notice Returns the payment amount in a given token for a USDC price.
     */
    function quotePayment(
        uint256 priceUsdc,
        PaymentToken paymentToken
    ) external view returns (uint256 amount, uint256 fee) {
        if (paymentToken == PaymentToken.USDC) {
            amount = priceUsdc;
            fee    = (amount * feeBps) / 10_000;
        } else if (paymentToken == PaymentToken.CLAW) {
            amount = _toTokenAmount(CLAW, priceUsdc);
            fee    = (amount * feeBps) / 10_000;
        } else {
            amount = _toTokenAmount(CLAWX, priceUsdc);
            uint256 effectiveBps = feeBps > clawxDiscountBps ? feeBps - clawxDiscountBps : 0;
            fee    = (amount * effectiveBps) / 10_000;
        }
    }

    // ─── Admin ────────────────────────────────────────────────────────────────

    /**
     * @notice Set exchange rate for CLAW or CLAWX.
     * @param token      CLAW or CLAWX address.
     * @param priceUsdc  How many USDC (6 dec) equals 1e18 of the token.
     *                   E.g. if 1 CLAW = 0.10 USDC → priceUsdc = 100_000 (0.10 × 1e6)
     */
    function setTokenPrice(address token, uint256 priceUsdc) external onlyRole(ADMIN_ROLE) {
        require(token == CLAW || token == CLAWX, "Unknown token");
        tokenPriceUsdc[token] = priceUsdc;
        emit TokenPriceSet(token, priceUsdc);
    }

    function setFeeBps(uint256 newBps) external onlyRole(ADMIN_ROLE) {
        require(newBps <= 500, "Fee too high"); // max 5%
        feeBps = newBps;
    }

    function setClawxDiscountBps(uint256 newDiscount) external onlyRole(ADMIN_ROLE) {
        require(newDiscount <= feeBps, "Discount cannot exceed fee");
        clawxDiscountBps = newDiscount;
    }

    function setBuyAndBurn(address newContract) external onlyRole(ADMIN_ROLE) {
        require(newContract != address(0), "Invalid address");
        buyAndBurnContract = newContract;
    }

    function setFeeWallet(address newWallet) external onlyRole(ADMIN_ROLE) {
        require(newWallet != address(0), "Invalid address");
        feeWallet = newWallet;
    }

    function pause()   external onlyRole(ADMIN_ROLE) { _pause(); }
    function unpause() external onlyRole(ADMIN_ROLE) { _unpause(); }

    // ─── Internal helpers ─────────────────────────────────────────────────────

    /**
     * @notice Convert a USDC price to token amount using oracle price.
     */
    function _toTokenAmount(address token, uint256 priceUsdc) internal view returns (uint256) {
        uint256 rate = tokenPriceUsdc[token];
        require(rate > 0, "Token price not set");
        // priceUsdc (6 dec) / rate (6 dec per 1e18 token) * 1e18 = token amount
        return (priceUsdc * 1e18) / rate;
    }

    /**
     * @notice Route protocol fees according to token type:
     *           - USDC:  50% → feeWallet, 50% → buyAndBurn (buys + burns CLAW)
     *           - CLAW:  100% → buyAndBurn
     *           - CLAWX: 100% → feeWallet
     */
    function _routeFee(address token, uint256 amount) internal {
        if (amount == 0) return;

        if (token == USDC) {
            uint256 half = amount / 2;
            IERC20(token).safeTransfer(feeWallet,         amount - half);
            IERC20(token).safeTransfer(buyAndBurnContract, half);
        } else if (token == CLAW) {
            IERC20(token).safeTransfer(buyAndBurnContract, amount);
            emit FeeBurned(token, amount);
        } else {
            // CLAWX → fee wallet
            IERC20(token).safeTransfer(feeWallet, amount);
        }
    }
}
