// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import "@openzeppelin/contracts/utils/Pausable.sol";
import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";

/**
 * @title  SmartWallet
 * @author ClawmarketAI
 * @notice Non-custodial wallet that lets autonomous AI agents transact
 *         within owner-defined spending limits on Base.
 *
 *         Key controls:
 *           - Owner sets a daily spending limit per agent address.
 *           - Transactions above `multisigThreshold` require M-of-N owner signatures.
 *           - Owner can pause ALL agent activity instantly (emergency stop).
 *           - Owner can revoke individual agent permissions at any time.
 *
 *         Supports ETH, USDC, $CLAW, and $CLAWX (any ERC-20).
 */
contract SmartWallet is ReentrancyGuard, Pausable {
    using SafeERC20 for IERC20;

    // ─── Roles ────────────────────────────────────────────────────────────────
    address public owner;

    // Agents authorized to call execute()
    mapping(address => bool) public isAgent;

    // ─── Daily spending limits ────────────────────────────────────────────────
    struct AgentLimit {
        uint256 dailyLimitUsdc;      // max USDC-equivalent per day (6 decimals)
        uint256 spentToday;          // USDC spent in the current period
        uint256 periodStart;         // timestamp of the current 24h window
        bool    active;              // agent is allowed to transact
    }
    mapping(address => AgentLimit) public agentLimits;

    // ─── Multisig (for transactions above threshold) ───────────────────────────
    uint256 public multisigThreshold;   // USDC amount above which multisig is required
    address[] public signers;           // M-of-N signer set
    uint256 public requiredSignatures;  // M

    struct PendingTx {
        address target;
        uint256 value;
        bytes   data;
        uint256 approvals;
        bool    executed;
        mapping(address => bool) approved;
    }
    mapping(bytes32 => PendingTx) private _pendingTxs;
    bytes32[] public pendingTxIds;

    // ─── Events ───────────────────────────────────────────────────────────────
    event AgentAdded(address indexed agent, uint256 dailyLimitUsdc);
    event AgentRevoked(address indexed agent);
    event AgentLimitChanged(address indexed agent, uint256 newLimit);
    event AgentPaused(address indexed agent);
    event AgentResumed(address indexed agent);
    event Executed(address indexed agent, address indexed target, uint256 value, bytes data);
    event MultisigTxProposed(bytes32 indexed txId, address indexed proposer);
    event MultisigTxApproved(bytes32 indexed txId, address indexed signer);
    event MultisigTxExecuted(bytes32 indexed txId);
    event MultisigThresholdChanged(uint256 newThreshold);
    event EtherReceived(address indexed sender, uint256 amount);

    // ─── Modifiers ────────────────────────────────────────────────────────────
    modifier onlyOwner() {
        require(msg.sender == owner, "SmartWallet: not owner");
        _;
    }

    modifier onlyAgent() {
        require(isAgent[msg.sender] && agentLimits[msg.sender].active,
                "SmartWallet: not an active agent");
        _;
    }

    modifier onlySigner() {
        require(_isSigner(msg.sender), "SmartWallet: not a signer");
        _;
    }

    // ─── Constructor ──────────────────────────────────────────────────────────
    constructor(
        address _owner,
        address[] memory _signers,
        uint256 _requiredSignatures,
        uint256 _multisigThreshold
    ) {
        require(_owner != address(0), "Invalid owner");
        require(_signers.length >= _requiredSignatures && _requiredSignatures > 0,
                "Invalid multisig config");

        owner                = _owner;
        signers              = _signers;
        requiredSignatures   = _requiredSignatures;
        multisigThreshold    = _multisigThreshold;
    }

    receive() external payable {
        emit EtherReceived(msg.sender, msg.value);
    }

    // ─── Agent management (owner only) ────────────────────────────────────────

    /**
     * @notice Add or update an agent with a daily USDC spending limit.
     * @param agent           Agent wallet address (the AI agent's EOA).
     * @param dailyLimitUsdc  Daily limit in USDC (6 decimals, e.g. 500e6 = 500 USDC).
     */
    function addAgent(address agent, uint256 dailyLimitUsdc) external onlyOwner {
        require(agent != address(0), "Invalid agent");
        isAgent[agent] = true;
        agentLimits[agent] = AgentLimit({
            dailyLimitUsdc: dailyLimitUsdc,
            spentToday:     0,
            periodStart:    block.timestamp,
            active:         true
        });
        emit AgentAdded(agent, dailyLimitUsdc);
    }

    /**
     * @notice Permanently revoke an agent's access.
     *         The owner decides when to stop the agent.
     */
    function revokeAgent(address agent) external onlyOwner {
        isAgent[agent] = false;
        agentLimits[agent].active = false;
        emit AgentRevoked(agent);
    }

    /**
     * @notice Temporarily pause a single agent without revoking it.
     */
    function pauseAgent(address agent) external onlyOwner {
        agentLimits[agent].active = false;
        emit AgentPaused(agent);
    }

    /**
     * @notice Resume a paused agent.
     */
    function resumeAgent(address agent) external onlyOwner {
        require(isAgent[agent], "Agent not registered");
        agentLimits[agent].active = true;
        emit AgentResumed(agent);
    }

    /**
     * @notice Update the daily spending limit for an agent.
     */
    function setAgentLimit(address agent, uint256 newLimit) external onlyOwner {
        require(isAgent[agent], "Agent not registered");
        agentLimits[agent].dailyLimitUsdc = newLimit;
        emit AgentLimitChanged(agent, newLimit);
    }

    /**
     * @notice Emergency: pause ALL agents instantly.
     */
    function pause()   external onlyOwner { _pause(); }
    function unpause() external onlyOwner { _unpause(); }

    // ─── Agent execution ──────────────────────────────────────────────────────

    /**
     * @notice Execute a transaction on behalf of the wallet.
     *         - If valueUsdc < multisigThreshold → executes immediately (within daily limit).
     *         - If valueUsdc >= multisigThreshold → creates a pending multisig tx.
     *
     * @param target    Contract to call.
     * @param value     ETH to send (in wei).
     * @param data      Calldata (ABI-encoded function call).
     * @param valueUsdc USDC-equivalent of this tx (for limit accounting, 6 decimals).
     */
    function execute(
        address target,
        uint256 value,
        bytes calldata data,
        uint256 valueUsdc
    ) external onlyAgent whenNotPaused nonReentrant returns (bytes memory result) {

        if (valueUsdc >= multisigThreshold) {
            // Route to multisig queue
            _proposeTx(target, value, data);
            return "";
        }

        // Check and update daily limit
        _checkAndUpdateDailyLimit(msg.sender, valueUsdc);

        result = _doCall(target, value, data);
        emit Executed(msg.sender, target, value, data);
    }

    /**
     * @notice Simplified execute for small amounts (no USDC accounting).
     *         Convenience method used by agents that don't need limit tracking.
     */
    function executeSimple(
        address target,
        uint256 value,
        bytes calldata data
    ) external onlyAgent whenNotPaused nonReentrant returns (bytes memory result) {
        result = _doCall(target, value, data);
        emit Executed(msg.sender, target, value, data);
    }

    // ─── Multisig flow ────────────────────────────────────────────────────────

    /**
     * @notice Signers approve a pending multisig transaction.
     */
    function approveTx(bytes32 txId) external onlySigner whenNotPaused {
        PendingTx storage ptx = _pendingTxs[txId];
        require(ptx.target != address(0), "Tx does not exist");
        require(!ptx.executed,            "Already executed");
        require(!ptx.approved[msg.sender],"Already approved");

        ptx.approved[msg.sender] = true;
        ptx.approvals++;
        emit MultisigTxApproved(txId, msg.sender);

        if (ptx.approvals >= requiredSignatures) {
            ptx.executed = true;
            _doCall(ptx.target, ptx.value, ptx.data);
            emit MultisigTxExecuted(txId);
        }
    }

    /**
     * @notice Update multisig threshold (owner only).
     */
    function setMultisigThreshold(uint256 newThreshold) external onlyOwner {
        multisigThreshold = newThreshold;
        emit MultisigThresholdChanged(newThreshold);
    }

    // ─── Token helpers ────────────────────────────────────────────────────────

    /**
     * @notice Withdraw ERC-20 tokens from the wallet (owner only).
     */
    function withdrawToken(address token, uint256 amount, address to) external onlyOwner {
        IERC20(token).safeTransfer(to, amount);
    }

    /**
     * @notice Withdraw ETH (owner only).
     */
    function withdrawEth(uint256 amount, address payable to) external onlyOwner {
        require(address(this).balance >= amount, "Insufficient ETH");
        (bool ok,) = to.call{value: amount}("");
        require(ok, "ETH transfer failed");
    }

    // ─── Internal helpers ─────────────────────────────────────────────────────

    function _checkAndUpdateDailyLimit(address agent, uint256 valueUsdc) internal {
        AgentLimit storage lim = agentLimits[agent];

        // Reset window if 24h elapsed
        if (block.timestamp >= lim.periodStart + 1 days) {
            lim.spentToday  = 0;
            lim.periodStart = block.timestamp;
        }

        require(
            lim.spentToday + valueUsdc <= lim.dailyLimitUsdc,
            "SmartWallet: daily limit exceeded"
        );
        lim.spentToday += valueUsdc;
    }

    function _proposeTx(address target, uint256 value, bytes calldata data) internal {
        bytes32 txId = keccak256(abi.encode(target, value, data, block.timestamp, msg.sender));
        PendingTx storage ptx = _pendingTxs[txId];
        ptx.target = target;
        ptx.value  = value;
        ptx.data   = data;
        pendingTxIds.push(txId);
        emit MultisigTxProposed(txId, msg.sender);
    }

    function _doCall(
        address target,
        uint256 value,
        bytes memory data
    ) internal returns (bytes memory) {
        require(target != address(0), "Invalid target");
        (bool success, bytes memory result) = target.call{value: value}(data);
        if (!success) {
            if (result.length > 0) {
                assembly { revert(add(result, 32), mload(result)) }
            }
            revert("SmartWallet: call failed");
        }
        return result;
    }

    function _isSigner(address account) internal view returns (bool) {
        for (uint256 i = 0; i < signers.length; i++) {
            if (signers[i] == account) return true;
        }
        return false;
    }

    // ─── View helpers ─────────────────────────────────────────────────────────

    /**
     * @notice Returns remaining daily budget for an agent (USDC, 6 decimals).
     */
    function remainingDailyLimit(address agent) external view returns (uint256) {
        AgentLimit storage lim = agentLimits[agent];
        if (block.timestamp >= lim.periodStart + 1 days) {
            return lim.dailyLimitUsdc; // window reset
        }
        uint256 spent = lim.spentToday;
        return lim.dailyLimitUsdc > spent ? lim.dailyLimitUsdc - spent : 0;
    }

    /**
     * @notice Returns pending tx count.
     */
    function pendingTxCount() external view returns (uint256) {
        return pendingTxIds.length;
    }
}
