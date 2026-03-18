// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @title clawmarketAI Escrow
/// @notice Holds funds trustlessly until delivery is confirmed by buyer
contract Escrow {

    enum State { AWAITING_DELIVERY, COMPLETE, DISPUTED, REFUNDED }

    struct Deal {
        uint256 id;
        address buyer;
        address seller;
        uint256 amount;
        State state;
        uint256 createdAt;
        uint256 timeoutAt;   // auto-release if no dispute after this timestamp
    }

    uint256 public dealCount;
    uint256 public constant TIMEOUT = 3 days;
    uint256 public constant PLATFORM_FEE_BPS = 100; // 1%
    address public owner;

    mapping(uint256 => Deal) public deals;

    event DealCreated(uint256 indexed id, address buyer, address seller, uint256 amount);
    event DealConfirmed(uint256 indexed id);
    event DealDisputed(uint256 indexed id);
    event DealRefunded(uint256 indexed id);
    event DealAutoReleased(uint256 indexed id);

    modifier onlyOwner() { require(msg.sender == owner, "Not owner"); _; }
    modifier onlyBuyer(uint256 id) { require(msg.sender == deals[id].buyer, "Not buyer"); _; }

    constructor() { owner = msg.sender; }

    /// @notice Buyer creates a deal — funds locked immediately
    function createDeal(address seller) external payable returns (uint256) {
        require(msg.value > 0, "Amount must be > 0");
        require(seller != msg.sender, "Buyer cannot be seller");

        uint256 id = ++dealCount;
        deals[id] = Deal({
            id: id,
            buyer: msg.sender,
            seller: seller,
            amount: msg.value,
            state: State.AWAITING_DELIVERY,
            createdAt: block.timestamp,
            timeoutAt: block.timestamp + TIMEOUT
        });

        emit DealCreated(id, msg.sender, seller, msg.value);
        return id;
    }

    /// @notice Buyer confirms delivery — releases funds to seller
    function confirmDelivery(uint256 id) external onlyBuyer(id) {
        Deal storage deal = deals[id];
        require(deal.state == State.AWAITING_DELIVERY, "Deal not active");

        deal.state = State.COMPLETE;

        uint256 fee = (deal.amount * PLATFORM_FEE_BPS) / 10000;
        uint256 sellerAmount = deal.amount - fee;

        (bool sent, ) = deal.seller.call{value: sellerAmount}("");
        require(sent, "Transfer to seller failed");

        emit DealConfirmed(id);
    }

    /// @notice Buyer raises a dispute — pauses auto-release, owner mediates
    function dispute(uint256 id) external onlyBuyer(id) {
        Deal storage deal = deals[id];
        require(deal.state == State.AWAITING_DELIVERY, "Deal not active");
        deal.state = State.DISPUTED;
        emit DealDisputed(id);
    }

    /// @notice Owner resolves dispute in favor of buyer (refund) or seller (release)
    function resolveDispute(uint256 id, bool refundBuyer) external onlyOwner {
        Deal storage deal = deals[id];
        require(deal.state == State.DISPUTED, "Not disputed");

        if (refundBuyer) {
            deal.state = State.REFUNDED;
            (bool sent, ) = deal.buyer.call{value: deal.amount}("");
            require(sent, "Refund failed");
            emit DealRefunded(id);
        } else {
            deal.state = State.COMPLETE;
            uint256 fee = (deal.amount * PLATFORM_FEE_BPS) / 10000;
            (bool sent, ) = deal.seller.call{value: deal.amount - fee}("");
            require(sent, "Release failed");
            emit DealConfirmed(id);
        }
    }

    /// @notice Anyone can trigger auto-release after timeout with no dispute
    function autoRelease(uint256 id) external {
        Deal storage deal = deals[id];
        require(deal.state == State.AWAITING_DELIVERY, "Deal not active");
        require(block.timestamp >= deal.timeoutAt, "Timeout not reached");

        deal.state = State.COMPLETE;
        uint256 fee = (deal.amount * PLATFORM_FEE_BPS) / 10000;
        (bool sent, ) = deal.seller.call{value: deal.amount - fee}("");
        require(sent, "Auto-release failed");

        emit DealAutoReleased(id);
    }

    function withdrawFees() external onlyOwner {
        payable(owner).transfer(address(this).balance);
    }
}
