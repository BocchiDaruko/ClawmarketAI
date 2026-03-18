// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @title clawmarketAI ReputationScore
/// @notice On-chain trust scoring for agents — built automatically from trade history
contract ReputationScore {

    struct Score {
        uint256 totalTrades;
        uint256 successfulTrades;
        uint256 disputesRaised;
        uint256 disputesLost;
        uint256 cumulativeRating;  // sum of all ratings (1–5 each)
        uint256 lastUpdated;
    }

    address public owner;
    address public marketplace;   // authorized to write scores

    mapping(address => Score) public scores;

    event ScoreUpdated(address indexed agent, bool success, uint8 rating);
    event DisputeRecorded(address indexed agent, bool lost);

    modifier onlyMarketplace() {
        require(msg.sender == marketplace || msg.sender == owner, "Not authorized");
        _;
    }

    constructor(address _marketplace) {
        owner = msg.sender;
        marketplace = _marketplace;
    }

    /// @notice Called after each completed trade to update the agent's score
    function recordTrade(address agent, bool success, uint8 rating) external onlyMarketplace {
        require(rating >= 1 && rating <= 5, "Rating must be 1-5");
        Score storage s = scores[agent];
        s.totalTrades++;
        if (success) s.successfulTrades++;
        s.cumulativeRating += rating;
        s.lastUpdated = block.timestamp;
        emit ScoreUpdated(agent, success, rating);
    }

    /// @notice Called when a dispute is raised or resolved against an agent
    function recordDispute(address agent, bool lost) external onlyMarketplace {
        Score storage s = scores[agent];
        s.disputesRaised++;
        if (lost) s.disputesLost++;
        s.lastUpdated = block.timestamp;
        emit DisputeRecorded(agent, lost);
    }

    /// @notice Returns the agent's average rating (scaled x100 for precision, e.g. 450 = 4.50)
    function getAverageRating(address agent) external view returns (uint256) {
        Score storage s = scores[agent];
        if (s.totalTrades == 0) return 0;
        return (s.cumulativeRating * 100) / s.totalTrades;
    }

    /// @notice Returns success rate as a percentage (0–100)
    function getSuccessRate(address agent) external view returns (uint256) {
        Score storage s = scores[agent];
        if (s.totalTrades == 0) return 0;
        return (s.successfulTrades * 100) / s.totalTrades;
    }

    /// @notice Returns true if the agent meets the minimum threshold
    function isTrusted(address agent, uint256 minTrades, uint256 minRating) external view returns (bool) {
        Score storage s = scores[agent];
        if (s.totalTrades < minTrades) return false;
        uint256 avg = (s.cumulativeRating * 100) / s.totalTrades;
        return avg >= minRating;
    }

    function getScore(address agent) external view returns (Score memory) {
        return scores[agent];
    }

    function setMarketplace(address _marketplace) external {
        require(msg.sender == owner, "Not owner");
        marketplace = _marketplace;
    }
}
