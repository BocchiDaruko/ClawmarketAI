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
 *  FIXES APPLIED:
 *   [1] createListing() — seller is always msg.sender (or authorized SmartWallet).
 *       Added SELLER_ROLE so SmartWallet agents can list on behalf of their owner.
 *   [2] approve() → forceApprove() via SafeERC20 (handles USDC allowance edge-cases).
 *   [3] MAX_LISTINGS_PER_SELLER cap to prevent spam from rogue agents.
 *   [4] Oracle price expiry: prices older than PRICE_EXPIRY_SECONDS are rejected.
 *
 *  Payment tokens:
 *    - USDC  : stable reference (6 decimals)
 *    - $CLAW : governance — 100% of fees → buyAndBurn
 *    - $CLAWX: utility   — 0.8% effective fee (0.2% discount)
 *
 *  Flow:
 *    1. Seller (or its SmartWallet) calls createListing()
 *    2. Buyer calls buy() → funds → Escrow.lock()
 *    3. Escrow releases to seller after delivery / auto-release
 *    4. ReputationScore updated for both parties
 */
contract Marketplace is AccessControl, ReentrancyGuard, Pausable {
    using SafeERC20 for IERC20;

    // ─────────────────────────────────────────────────────────────────────────
    //  ROLES
    // ─────────────────────────────────────────────────────────────────────────

    bytes32 public constant ADMIN_ROLE    = keccak256("ADMIN_ROLE");
    bytes32 public constant OPERATOR_ROLE = keccak256("OPERATOR_ROLE");
    /// @dev Granted to SmartWallet contracts so agents can list on behalf of owners.
    bytes32 public constant SELLER_ROLE   = keccak256("SELLER_ROLE");

    // ─────────────────────────────────────────────────────────────────────────
    //  CONSTANTS
    // ─────────────────────────────────────────────────────────────────────────

    uint256 public constant MAX_FEE_BPS             = 500;     // 5% hard cap
    uint256 public constant MAX_LISTINGS_PER_SELLER = 500;     // [FIX-3] spam protection
    uint256 public constant PRICE_EXPIRY_SECONDS    = 1 hours; // [FIX-4] oracle freshness

    // ─────────────────────────────────────────────────────────────────────────
    //  TOKEN ADDRESSES (Base Mainnet)
    // ─────────────────────────────────────────────────────────────────────────

    address public immutable USDC;   // 0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913
    address public immutable CLAW;
    address public immutable CLAWX;

    // ─────────────────────────────────────────────────────────────────────────
    //  FEE CONFIG
    // ─────────────────────────────────────────────────────────────────────────

    uint256 public feeBps           = 100;  // 1.0% base fee
    uint256 public clawxDiscountBps = 20;   // 0.2% discount → effective 0.8%
    address public feeWallet;
    address public buyAndBurnContract;

    // ─────────────────────────────────────────────────────────────────────────
    //  EXTERNAL CONTRACTS
    // ─────────────────────────────────────────────────────────────────────────

    Escrow          public escrow;
    ReputationScore public reputation;

    // ─────────────────────────────────────────────────────────────────────────
    //  LISTING STORAGE
    // ─────────────────────────────────────────────────────────────────────────

    enum PaymentToken { USDC, CLAW, CLAWX }

    struct Listing {
        uint256 listingId;
        address seller;
        uint256 priceUsdc;      // reference price in USDC (6 decimals)
        string  category;
        string  metadataUri;    // ipfs:// URI
        bool    available;
        uint256 createdAt;
        uint256 soldAt;
    }

    uint256 private _nextListingId = 1;
    mapping(uint256 => Listing)   public listings;
    mapping(address => uint256[]) public sellerListings;

    // [FIX-3] active listing count per seller
    mapping(address => uint256) public activeListingCount;

    // ─────────────────────────────────────────────────────────────────────────
    //  ORACLE  [FIX-4: price + timestamp]
    // ─────────────────────────────────────────────────────────────────────────

    struct OraclePrice {
        uint256 priceUsdc;  // USDC (6 dec) per 1e18 of token
        uint256 updatedAt;  // block.timestamp when set
    }
    mapping(address => OraclePrice) public tokenOracle;

    // ─────────────────────────────────────────────────────────────────────────
    //  EVENTS
    // ─────────────────────────────────────────────────────────────────────────

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
    event TokenPriceSet(address token, uint256 priceUsdc, uint256 timestamp);

    // ─────────────────────────────────────────────────────────────────────────
    //  CONSTRUCTOR
    // ─────────────────────────────────────────────────────────────────────────

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
        require(admin       != address(0), "Invalid admin");
        require(_usdc       != address(0), "Invalid USDC");
        require(_claw       != address(0), "Invalid CLAW");
        require(_clawx      != address(0), "Invalid CLAWX");
        require(_feeWallet  != address(0), "Invalid feeWallet");
        require(_buyAndBurn != address(0), "Invalid buyAndBurn");
        require(_escrow     != address(0), "Invalid escrow");
        require(_reputation != address(0), "Invalid reputation");

        _grantRole(DEFAULT_ADMIN_ROLE, admin);
        _grantRole(ADMIN_ROLE,         admin);

        USDC               = _usdc;
        CLAW               = _claw;
        CLAWX              = _clawx;
        feeWallet          = _feeWallet;
        buyAndBurnContract = _buyAndBurn;
        escrow             = Escrow(payable(_escrow));
        reputation         = ReputationScore(_reputation);
    }

    // ─────────────────────────────────────────────────────────────────────────
    //  LISTING MANAGEMENT
    // ─────────────────────────────────────────────────────────────────────────

    /**
     * @notice Create a new listing.
     * @dev    [FIX-1] seller is always msg.sender.
     *         SmartWallet contracts must hold SELLER_ROLE and pass their owner
     *         as `sellerOwner` — the address that will receive escrow funds.
     *         Regular EOA sellers pass sellerOwner == address(0) (ignored).
     *
     * @param priceUsdc   Price in USDC (6 decimals).
     * @param category    Good category string.
     * @param metadataUri IPFS URI.
     * @param sellerOwner If msg.sender has SELLER_ROLE (SmartWallet), the actual
     *                    owner address. Pass address(0) for direct EOA sellers.
     */
    function createListing(
        uint256 priceUsdc,
        string calldata category,
        string calldata metadataUri,
        address sellerOwner
    ) external whenNotPaused returns (uint256 listingId) {
        // [FIX-1] Determine effective seller
        address seller;
        if (hasRole(SELLER_ROLE, msg.sender)) {
            require(sellerOwner != address(0), "SmartWallet must provide sellerOwner");
            seller = sellerOwner;
        } else {
            seller = msg.sender;
        }

        require(priceUsdc > 0,                 "Price must be > 0");
        require(bytes(category).length > 0,    "Category required");
        require(bytes(metadataUri).length > 0, "MetadataUri required");

        // [FIX-3] Enforce listing cap
        require(
            activeListingCount[seller] < MAX_LISTINGS_PER_SELLER,
            "Listing cap reached"
        );

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
        activeListingCount[seller]++;

        emit ListingCreated(listingId, seller, priceUsdc, category, metadataUri);
    }

    /**
     * @notice Update the price of an active listing. Seller or operator only.
     */
    function updatePrice(uint256 listingId, uint256 newPriceUsdc)
        external
        whenNotPaused
    {
        Listing storage lst = listings[listingId];
        require(lst.available, "Listing not available");
        require(
            lst.seller == msg.sender || hasRole(OPERATOR_ROLE, msg.sender),
            "Not seller"
        );
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
        require(
            lst.seller == msg.sender || hasRole(OPERATOR_ROLE, msg.sender),
            "Not seller"
        );
        lst.available = false;
        activeListingCount[lst.seller]--;
        emit ListingCancelled(listingId, lst.seller);
    }

    // ─────────────────────────────────────────────────────────────────────────
    //  BUY
    // ─────────────────────────────────────────────────────────────────────────

    /**
     * @notice Purchase a listing.
     * @param listingId    The listing to buy.
     * @param paymentToken USDC / CLAW / CLAWX.
     * @param autoRelease  Whether escrow auto-releases after delay.
     */
    function buy(
        uint256      listingId,
        PaymentToken paymentToken,
        bool         autoRelease
    ) external nonReentrant whenNotPaused {
        Listing storage lst = listings[listingId];
        require(lst.available,            "Listing not available");
        require(lst.seller != msg.sender, "Seller cannot buy own listing");

        lst.available = false;
        lst.soldAt    = block.timestamp;
        activeListingCount[lst.seller]--;

        // ── Compute payment & fee ─────────────────────────────────────────────
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
            // CLAWX with discount
            token         = CLAWX;
            paymentAmount = _toTokenAmount(CLAWX, lst.priceUsdc);
            uint256 effectiveBps = feeBps > clawxDiscountBps
                ? feeBps - clawxDiscountBps
                : 0;
            feeAmount = (paymentAmount * effectiveBps) / 10_000;
        }

        uint256 escrowAmount = paymentAmount - feeAmount;

        // ── Pull full amount from buyer ────────────────────────────────────────
        IERC20(token).safeTransferFrom(msg.sender, address(this), paymentAmount);

        // ── Route fee ─────────────────────────────────────────────────────────
        _routeFee(token, feeAmount);

        // ── [FIX-2] forceApprove before escrow pull ───────────────────────────
        IERC20(token).forceApprove(address(escrow), escrowAmount);

        // ── Lock in Escrow ────────────────────────────────────────────────────
        escrow.lock(
            listingId,
            msg.sender,
            lst.seller,
            token,
            escrowAmount,
            autoRelease
        );

        // ── Update reputation (non-blocking) ─────────────────────────────────
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

    // ─────────────────────────────────────────────────────────────────────────
    //  VIEW HELPERS
    // ─────────────────────────────────────────────────────────────────────────

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

    function getSellerListings(address seller)
        external view returns (uint256[] memory)
    {
        return sellerListings[seller];
    }

    /**
     * @notice Quote payment amount + fee for a given USDC price and token.
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
            uint256 effectiveBps = feeBps > clawxDiscountBps
                ? feeBps - clawxDiscountBps : 0;
            fee = (amount * effectiveBps) / 10_000;
        }
    }

    // ─────────────────────────────────────────────────────────────────────────
    //  ADMIN
    // ─────────────────────────────────────────────────────────────────────────

    /**
     * @notice Set oracle price for CLAW or CLAWX.
     * @param token      CLAW or CLAWX address.
     * @param priceUsdc  USDC (6 dec) per 1e18 of token.
     *                   E.g. 1 CLAW = 0.10 USDC → priceUsdc = 100_000
     */
    function setTokenPrice(address token, uint256 priceUsdc)
        external
        onlyRole(ADMIN_ROLE)
    {
        require(token == CLAW || token == CLAWX, "Unknown token");
        require(priceUsdc > 0, "Price must be > 0");
        // [FIX-4] Store timestamp alongside price
        tokenOracle[token] = OraclePrice({
            priceUsdc: priceUsdc,
            updatedAt: block.timestamp
        });
        emit TokenPriceSet(token, priceUsdc, block.timestamp);
    }

    function setFeeBps(uint256 newBps) external onlyRole(ADMIN_ROLE) {
        require(newBps <= MAX_FEE_BPS, "Fee too high");
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

    // ─────────────────────────────────────────────────────────────────────────
    //  INTERNAL HELPERS
    // ─────────────────────────────────────────────────────────────────────────

    /**
     * @notice Convert USDC price to token amount using oracle.
     *         [FIX-4] Reverts if oracle price is stale.
     */
    function _toTokenAmount(address token, uint256 priceUsdc)
        internal view returns (uint256)
    {
        OraclePrice storage oracle = tokenOracle[token];
        require(oracle.priceUsdc > 0, "Token price not set");
        require(
            block.timestamp - oracle.updatedAt <= PRICE_EXPIRY_SECONDS,
            "Oracle price is stale"
        );
        return (priceUsdc * 1e18) / oracle.priceUsdc;
    }

    /**
     * @notice Route protocol fees:
     *           USDC  → 50% feeWallet / 50% buyAndBurn
     *           CLAW  → 100% buyAndBurn (deflationary)
     *           CLAWX → 100% feeWallet
     */
    function _routeFee(address token, uint256 amount) internal {
        if (amount == 0) return;

        if (token == USDC) {
            uint256 half = amount / 2;
            IERC20(token).safeTransfer(feeWallet,          amount - half);
            IERC20(token).safeTransfer(buyAndBurnContract, half);
        } else if (token == CLAW) {
            IERC20(token).safeTransfer(buyAndBurnContract, amount);
            emit FeeBurned(token, amount);
        } else {
            IERC20(token).safeTransfer(feeWallet, amount);
        }
    }
}
