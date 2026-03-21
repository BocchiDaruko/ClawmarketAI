// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "@openzeppelin/contracts/access/AccessControl.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import "@openzeppelin/contracts/utils/Pausable.sol";

/**
 * @title  ReputationScore
 * @author ClawmarketAI
 * @notice On-chain reputation system for marketplace participants.
 *         Scores range from 0 to 10,000 (100.00 in display format).
 *
 *         Score sources:
 *           1. Internal events — trades, disputes, fulfilments (via UPDATER_ROLE)
 *           2. External oracle  — Chainlink / API3 off-chain data (via ORACLE_ROLE)
 *
 *         Weight: internal 70%, oracle 30% (configurable by ADMIN).
 */
contract ReputationScore is AccessControl, ReentrancyGuard, Pausable {

    // ─── Roles ────────────────────────────────────────────────────────────────
    bytes32 public constant ADMIN_ROLE   = keccak256("ADMIN_ROLE");
    bytes32 public constant UPDATER_ROLE = keccak256("UPDATER_ROLE"); // Marketplace + Escrow
    bytes32 public constant ORACLE_ROLE  = keccak256("ORACLE_ROLE");  // Chainlink / API3 adapter

    // ─── Constants ────────────────────────────────────────────────────────────
    uint256 public constant MAX_SCORE         = 10_000; // 100.00
    uint256 public constant INITIAL_SCORE     = 5_000;  // 50.00 — neutral start
    uint256 public constant MIN_TRADES_RATED  = 3;      // min trades before oracle weight applies

    // ─── Score storage ────────────────────────────────────────────────────────
    struct AccountScore {
        uint256 internalScore;   // 0–10000, from on-chain events
        uint256 oracleScore;     // 0–10000, from external oracle
        uint256 tradeCount;      // total completed trades
        uint256 disputesLost;    // disputes decided against this account
        uint256 lastUpdated;     // block.timestamp of last update
        bool    initialized;
    }

    mapping(address => AccountScore) private _scores;

    // ─── Oracle weight (basis points, 3000 = 30%) ─────────────────────────────
    uint256 public oracleWeightBps = 3_000;   // 30% oracle, 70% internal

    // ─── Events ───────────────────────────────────────────────────────────────
    event ScoreInitialized(address indexed account, uint256 score);
    event InternalScoreUpdated(address indexed account, uint256 oldScore, uint256 newScore, string reason);
    event OracleScoreUpdated(address indexed account, uint256 oldScore, uint256 newScore);
    event OracleWeightChanged(uint256 oldBps, uint256 newBps);
    event DisputeLost(address indexed account, uint256 penalty);

    // ─── Constructor ──────────────────────────────────────────────────────────
    constructor(address admin) {
        _grantRole(DEFAULT_ADMIN_ROLE, admin);
        _grantRole(ADMIN_ROLE,         admin);
    }

    // ─── Score read ───────────────────────────────────────────────────────────

    /**
     * @notice Returns the composite score for an account (0–10000).
     *         Used by Buyer Agent and Strategy Engine.
     */
    function getScore(address account) external view returns (uint256) {
        return _compositeScore(account);
    }

    /**
     * @notice Returns full score breakdown for an account.
     */
    function getScoreDetails(address account) external view returns (
        uint256 composite,
        uint256 internalScore,
        uint256 oracleScore,
        uint256 tradeCount,
        uint256 disputesLost,
        uint256 lastUpdated
    ) {
        AccountScore storage s = _scores[account];
        composite     = _compositeScore(account);
        internalScore = s.initialized ? s.internalScore : INITIAL_SCORE;
        oracleScore   = s.initialized ? s.oracleScore   : INITIAL_SCORE;
        tradeCount    = s.tradeCount;
        disputesLost  = s.disputesLost;
        lastUpdated   = s.lastUpdated;
    }

    // ─── Internal score updates (Marketplace / Escrow) ────────────────────────

    /**
     * @notice Called by Marketplace/Escrow after a successful trade.
     *         Increases seller score; smaller boost for buyers.
     */
    function recordSuccessfulTrade(
        address seller,
        address buyer
    ) external onlyRole(UPDATER_ROLE) whenNotPaused {
        _ensureInitialized(seller);
        _ensureInitialized(buyer);

        // Seller gets a larger boost for successful delivery
        _adjustInternalScore(seller, 50, true, "trade_success_seller");
        // Buyer gets a smaller boost for completing payment
        _adjustInternalScore(buyer,  20, true, "trade_success_buyer");

        _scores[seller].tradeCount++;
        _scores[buyer].tradeCount++;
    }

    /**
     * @notice Called by Escrow when a dispute is resolved against an account.
     */
    function recordDisputeLost(
        address account,
        uint256 penaltyPoints
    ) external onlyRole(UPDATER_ROLE) whenNotPaused {
        _ensureInitialized(account);
        uint256 penalty = penaltyPoints == 0 ? 200 : penaltyPoints;
        _adjustInternalScore(account, penalty, false, "dispute_lost");
        _scores[account].disputesLost++;
        emit DisputeLost(account, penalty);
    }

    /**
     * @notice Called when a seller fails to fulfil an order.
     */
    function recordFulfilmentFailure(
        address seller
    ) external onlyRole(UPDATER_ROLE) whenNotPaused {
        _ensureInitialized(seller);
        _adjustInternalScore(seller, 150, false, "fulfilment_failure");
    }

    /**
     * @notice Called when a buyer cancels a legitimate order (minor penalty).
     */
    function recordBuyerCancellation(
        address buyer
    ) external onlyRole(UPDATER_ROLE) whenNotPaused {
        _ensureInitialized(buyer);
        _adjustInternalScore(buyer, 30, false, "buyer_cancellation");
    }

    // ─── Oracle score updates ─────────────────────────────────────────────────

    /**
     * @notice Called by the oracle adapter (Chainlink / API3) to push an
     *         externally-derived reputation score.
     * @param account   Wallet address being scored.
     * @param score     New oracle score (0–10000).
     */
    function updateOracleScore(
        address account,
        uint256 score
    ) external onlyRole(ORACLE_ROLE) whenNotPaused {
        require(score <= MAX_SCORE, "Score exceeds maximum");
        _ensureInitialized(account);

        uint256 old = _scores[account].oracleScore;
        _scores[account].oracleScore  = score;
        _scores[account].lastUpdated  = block.timestamp;

        emit OracleScoreUpdated(account, old, score);
    }

    // ─── Admin ────────────────────────────────────────────────────────────────

    /**
     * @notice Adjust the weight of the oracle vs internal score.
     * @param newWeightBps  Oracle weight in basis points (max 5000 = 50%).
     */
    function setOracleWeight(uint256 newWeightBps) external onlyRole(ADMIN_ROLE) {
        require(newWeightBps <= 5_000, "Oracle weight cannot exceed 50%");
        emit OracleWeightChanged(oracleWeightBps, newWeightBps);
        oracleWeightBps = newWeightBps;
    }

    function pause()   external onlyRole(ADMIN_ROLE) { _pause(); }
    function unpause() external onlyRole(ADMIN_ROLE) { _unpause(); }

    // ─── Internal helpers ─────────────────────────────────────────────────────

    function _compositeScore(address account) internal view returns (uint256) {
        AccountScore storage s = _scores[account];
        if (!s.initialized) return INITIAL_SCORE;

        // Only apply oracle weight if the account has enough trading history
        if (s.tradeCount < MIN_TRADES_RATED) {
            return s.internalScore;
        }

        uint256 oWeight  = oracleWeightBps;
        uint256 iWeight  = 10_000 - oWeight;
        return (s.internalScore * iWeight + s.oracleScore * oWeight) / 10_000;
    }

    function _adjustInternalScore(
        address account,
        uint256 delta,
        bool    increase,
        string memory reason
    ) internal {
        AccountScore storage s = _scores[account];
        uint256 old  = s.internalScore;
        uint256 next;

        if (increase) {
            next = old + delta > MAX_SCORE ? MAX_SCORE : old + delta;
        } else {
            next = old > delta ? old - delta : 0;
        }

        s.internalScore = next;
        s.lastUpdated   = block.timestamp;
        emit InternalScoreUpdated(account, old, next, reason);
    }

    function _ensureInitialized(address account) internal {
        if (!_scores[account].initialized) {
            _scores[account] = AccountScore({
                internalScore: INITIAL_SCORE,
                oracleScore:   INITIAL_SCORE,
                tradeCount:    0,
                disputesLost:  0,
                lastUpdated:   block.timestamp,
                initialized:   true
            });
            emit ScoreInitialized(account, INITIAL_SCORE);
        }
    }
}
