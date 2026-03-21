// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "@openzeppelin/contracts/access/AccessControl.sol";
import "@openzeppelin/contracts/utils/Pausable.sol";

/**
 * @title  ReputationScore
 * @author ClawmarketAI
 * @notice On-chain reputation system for marketplace participants on Base.
 *         Scores range from 0 to 10,000 (100.00 in display format).
 *
 *  FIXES APPLIED:
 *   [1] Removed unused ReentrancyGuard import — saves deploy gas, removes confusion.
 *   [2] penaltyPoints capped at MAX_PENALTY (500) in recordDisputeLost() —
 *       prevents a single dispute from zeroing out a score.
 *   [3] getBatchScores() added — agents can query multiple accounts in one call.
 *   [5] recordDisputeLost() now callable by Escrow via UPDATER_ROLE.
 *       Escrow.resolveDispute() should call reputation.recordDisputeLost(loser, 0)
 *       after granting Escrow the UPDATER_ROLE.
 *
 *  Score sources:
 *    1. Internal events — trades, disputes, fulfilments (UPDATER_ROLE)
 *    2. External oracle  — Chainlink / API3 off-chain data (ORACLE_ROLE)
 *
 *  Weight: internal 70%, oracle 30% (configurable by ADMIN, max 50% oracle).
 *  Oracle weight only applies after MIN_TRADES_RATED completed trades.
 */
contract ReputationScore is AccessControl, Pausable {

    // ─────────────────────────────────────────────────────────────────────────
    //  ROLES
    // ─────────────────────────────────────────────────────────────────────────

    bytes32 public constant ADMIN_ROLE   = keccak256("ADMIN_ROLE");
    bytes32 public constant UPDATER_ROLE = keccak256("UPDATER_ROLE"); // Marketplace + Escrow
    bytes32 public constant ORACLE_ROLE  = keccak256("ORACLE_ROLE");  // Chainlink / API3 adapter

    // ─────────────────────────────────────────────────────────────────────────
    //  CONSTANTS
    // ─────────────────────────────────────────────────────────────────────────

    uint256 public constant MAX_SCORE        = 10_000; // 100.00
    uint256 public constant INITIAL_SCORE    = 5_000;  // 50.00 — neutral start
    uint256 public constant MIN_TRADES_RATED = 3;      // min trades before oracle weight applies

    // [FIX-2] Max penalty a single dispute can apply
    uint256 public constant MAX_PENALTY      = 500;    // 5.00 points max per dispute

    // ─────────────────────────────────────────────────────────────────────────
    //  STORAGE
    // ─────────────────────────────────────────────────────────────────────────

    struct AccountScore {
        uint256 internalScore;   // 0–10000, from on-chain events
        uint256 oracleScore;     // 0–10000, from external oracle
        uint256 tradeCount;      // total completed trades
        uint256 disputesLost;    // disputes decided against this account
        uint256 lastUpdated;     // block.timestamp of last update
        bool    initialized;
    }

    mapping(address => AccountScore) private _scores;

    // ─────────────────────────────────────────────────────────────────────────
    //  ORACLE WEIGHT
    // ─────────────────────────────────────────────────────────────────────────

    /// @dev Oracle weight in basis points. 3000 = 30% oracle, 70% internal.
    uint256 public oracleWeightBps = 3_000;

    // ─────────────────────────────────────────────────────────────────────────
    //  EVENTS
    // ─────────────────────────────────────────────────────────────────────────

    event ScoreInitialized(address indexed account, uint256 score);
    event InternalScoreUpdated(
        address indexed account,
        uint256 oldScore,
        uint256 newScore,
        string  reason
    );
    event OracleScoreUpdated(address indexed account, uint256 oldScore, uint256 newScore);
    event OracleWeightChanged(uint256 oldBps, uint256 newBps);
    event DisputeLost(address indexed account, uint256 penalty);

    // ─────────────────────────────────────────────────────────────────────────
    //  CONSTRUCTOR
    // ─────────────────────────────────────────────────────────────────────────

    constructor(address admin) {
        require(admin != address(0), "Invalid admin");
        _grantRole(DEFAULT_ADMIN_ROLE, admin);
        _grantRole(ADMIN_ROLE,         admin);
    }

    // ─────────────────────────────────────────────────────────────────────────
    //  SCORE READ
    // ─────────────────────────────────────────────────────────────────────────

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

    /**
     * @notice [FIX-3] Batch query — returns composite scores for multiple accounts.
     *         Allows Buyer Agents to evaluate multiple sellers in a single RPC call.
     * @param accounts  Array of wallet addresses to query.
     * @return scores   Composite scores in the same order as input.
     */
    function getBatchScores(address[] calldata accounts)
        external
        view
        returns (uint256[] memory scores)
    {
        scores = new uint256[](accounts.length);
        for (uint256 i = 0; i < accounts.length; i++) {
            scores[i] = _compositeScore(accounts[i]);
        }
    }

    // ─────────────────────────────────────────────────────────────────────────
    //  INTERNAL SCORE UPDATES  (Marketplace / Escrow via UPDATER_ROLE)
    // ─────────────────────────────────────────────────────────────────────────

    /**
     * @notice Called by Marketplace after a successful trade.
     *         Seller gets a larger boost; buyer gets a smaller boost.
     */
    function recordSuccessfulTrade(
        address seller,
        address buyer
    ) external onlyRole(UPDATER_ROLE) whenNotPaused {
        _ensureInitialized(seller);
        _ensureInitialized(buyer);

        _adjustInternalScore(seller, 50, true,  "trade_success_seller");
        _adjustInternalScore(buyer,  20, true,  "trade_success_buyer");

        _scores[seller].tradeCount++;
        _scores[buyer].tradeCount++;
    }

    /**
     * @notice Called by Escrow when a dispute is resolved against an account.
     * @dev    [FIX-2] penaltyPoints is capped at MAX_PENALTY (500).
     *         [FIX-5] Escrow must hold UPDATER_ROLE to call this.
     *                 Call from Escrow.resolveDispute() after determining the loser.
     *
     * @param account       Account that lost the dispute.
     * @param penaltyPoints Penalty to apply (0 = default 200). Capped at MAX_PENALTY.
     */
    function recordDisputeLost(
        address account,
        uint256 penaltyPoints
    ) external onlyRole(UPDATER_ROLE) whenNotPaused {
        _ensureInitialized(account);

        // [FIX-2] Cap penalty — prevents single dispute from zeroing score
        uint256 penalty = penaltyPoints == 0
            ? 200
            : _min(penaltyPoints, MAX_PENALTY);

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

    // ─────────────────────────────────────────────────────────────────────────
    //  ORACLE SCORE UPDATES  (Chainlink / API3 adapter via ORACLE_ROLE)
    // ─────────────────────────────────────────────────────────────────────────

    /**
     * @notice Push an externally-derived reputation score.
     * @param account  Wallet address being scored.
     * @param score    New oracle score (0–10000).
     */
    function updateOracleScore(
        address account,
        uint256 score
    ) external onlyRole(ORACLE_ROLE) whenNotPaused {
        require(score <= MAX_SCORE, "Score exceeds maximum");
        _ensureInitialized(account);

        uint256 old = _scores[account].oracleScore;
        _scores[account].oracleScore = score;
        _scores[account].lastUpdated = block.timestamp;

        emit OracleScoreUpdated(account, old, score);
    }

    // ─────────────────────────────────────────────────────────────────────────
    //  ADMIN
    // ─────────────────────────────────────────────────────────────────────────

    /**
     * @notice Adjust oracle vs internal weight.
     * @param newWeightBps Oracle weight in basis points (max 5000 = 50%).
     */
    function setOracleWeight(uint256 newWeightBps) external onlyRole(ADMIN_ROLE) {
        require(newWeightBps <= 5_000, "Oracle weight cannot exceed 50%");
        emit OracleWeightChanged(oracleWeightBps, newWeightBps);
        oracleWeightBps = newWeightBps;
    }

    function pause()   external onlyRole(ADMIN_ROLE) { _pause(); }
    function unpause() external onlyRole(ADMIN_ROLE) { _unpause(); }

    // ─────────────────────────────────────────────────────────────────────────
    //  INTERNAL HELPERS
    // ─────────────────────────────────────────────────────────────────────────

    function _compositeScore(address account) internal view returns (uint256) {
        AccountScore storage s = _scores[account];
        if (!s.initialized) return INITIAL_SCORE;

        // Oracle weight only applies after enough trading history
        if (s.tradeCount < MIN_TRADES_RATED) {
            return s.internalScore;
        }

        uint256 oWeight = oracleWeightBps;
        uint256 iWeight = 10_000 - oWeight;
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

    /// @dev [FIX-2] Helper to cap penalty values.
    function _min(uint256 a, uint256 b) internal pure returns (uint256) {
        return a < b ? a : b;
    }
}
