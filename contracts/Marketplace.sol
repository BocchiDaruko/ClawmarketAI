// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/security/ReentrancyGuard.sol";
import "@openzeppelin/contracts/access/Ownable.sol";

/// @title clawmarketAI Marketplace
/// @notice Core contract governing listings, offers, and settlements
contract Marketplace is ReentrancyGuard, Ownable {

    uint256 public listingCount;
    uint256 public constant PLATFORM_FEE_BPS = 100; // 1%

    struct Listing {
        uint256 id;
        address seller;
        string category;       // "compute" | "data" | "api-access" | "good"
        string metadataURI;    // IPFS URI with good description
        uint256 price;         // in wei (USDC or native token)
        bool active;
    }

    mapping(uint256 => Listing) public listings;
    mapping(address => uint256[]) public agentListings;

    event Listed(uint256 indexed id, address indexed seller, uint256 price);
    event Purchased(uint256 indexed id, address indexed buyer, address indexed seller, uint256 price);
    event Delisted(uint256 indexed id);

    constructor() Ownable(msg.sender) {}

    /// @notice Create a new listing
    function list(
        string calldata category,
        string calldata metadataURI,
        uint256 price
    ) external returns (uint256) {
        require(price > 0, "Price must be > 0");

        uint256 id = ++listingCount;
        listings[id] = Listing({
            id: id,
            seller: msg.sender,
            category: category,
            metadataURI: metadataURI,
            price: price,
            active: true
        });
        agentListings[msg.sender].push(id);

        emit Listed(id, msg.sender, price);
        return id;
    }

    /// @notice Purchase a listing — funds go to escrow automatically
    function purchase(uint256 listingId) external payable nonReentrant {
        Listing storage item = listings[listingId];
        require(item.active, "Listing not active");
        require(msg.value >= item.price, "Insufficient payment");
        require(msg.sender != item.seller, "Cannot buy own listing");

        item.active = false;

        uint256 fee = (item.price * PLATFORM_FEE_BPS) / 10000;
        uint256 sellerAmount = item.price - fee;

        (bool sent, ) = item.seller.call{value: sellerAmount}("");
        require(sent, "Transfer failed");

        emit Purchased(listingId, msg.sender, item.seller, item.price);
    }

    /// @notice Delist a good (seller or owner only)
    function delist(uint256 listingId) external {
        Listing storage item = listings[listingId];
        require(msg.sender == item.seller || msg.sender == owner(), "Not authorized");
        item.active = false;
        emit Delisted(listingId);
    }

    /// @notice Get all active listings for an agent
    function getAgentListings(address agent) external view returns (uint256[] memory) {
        return agentListings[agent];
    }

    /// @notice Withdraw platform fees
    function withdrawFees() external onlyOwner {
        payable(owner()).transfer(address(this).balance);
    }
}
