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
 *  FIXES APPLIED:
 *   [1] executeSimple() removed — all agent calls go through daily limit check.
 *       Pass valueUsdc = 0 for non-financial calls (metadata updates, etc).
 *   [2] Nonce added to _proposeTx() — prevents txId collision within same block.
 *   [3] Execution timelock — multisig txs require executionDelay after reaching
 *       M approvals. executeTx() must be called explicitly after delay expires.
 *   [4] pendingTxIds cleaned up via swap-and-pop — O(1) removal.
 *       cancelTx() added for owner to cancel pending/approved txs.
 *   [5] Two-step ownership transfer — proposeOwner() + acceptOwnership().
 */
contract SmartWallet is ReentrancyGuard, Pausable {
    using SafeERC20 for IERC20;

    // ─────────────────────────────────────────────────────────────────────────
    //  OWNERSHIP  [FIX-5]
    // ─────────────────────────────────────────────────────────────────────────

    address public owner;
    address public pendingOwner;

    modifier onlyOwner() {
        require(msg.sender == owner, "SmartWallet: not owner");
        _;
    }

    // ─────────────────────────────────────────────────────────────────────────
    //  AGENTS
    // ─────────────────────────────────────────────────────────────────────────

    mapping(address => bool) public isAgent;

    struct AgentLimit {
        uint256 dailyLimitUsdc; // max USDC-equivalent per day (6 decimals)
        uint256 spentToday;     // USDC spent in current 24h window
        uint256 periodStart;    // start of current 24h window
        bool    active;
    }
    mapping(address => AgentLimit) public agentLimits;

    modifier onlyAgent() {
        require(
            isAgent[msg.sender] && agentLimits[msg.sender].active,
            "SmartWallet: not an active agent"
        );
        _;
    }

    // ─────────────────────────────────────────────────────────────────────────
    //  MULTISIG  [FIX-2: nonce | FIX-3: timelock | FIX-4: cleanup]
    // ─────────────────────────────────────────────────────────────────────────

    uint256 public multisigThreshold;
    address[] public signers;
    uint256 public requiredSignatures;

    /// @dev [FIX-3] Delay between full approval and execution. Default: 1 hour.
    uint256 public executionDelay = 1 hours;

    /// @dev [FIX-2] Monotonic nonce to prevent txId collisions.
    uint256 private _nonce;

    enum TxStatus { Pending, Approved, Executed, Cancelled }

    struct PendingTx {
        address  target;
        uint256  value;
        bytes    data;
        uint256  approvals;
        TxStatus status;
        uint256  approvedAt; // [FIX-3] timestamp when M approvals were reached
        mapping(address => bool) approved;
    }

    mapping(bytes32 => PendingTx) private _pendingTxs;

    /// @dev [FIX-4] Only active (non-executed, non-cancelled) txIds live here.
    bytes32[] public pendingTxIds;
    mapping(bytes32 => uint256) private _txIdIndex;

    modifier onlySigner() {
        require(_isSigner(msg.sender), "SmartWallet: not a signer");
        _;
    }

    // ─────────────────────────────────────────────────────────────────────────
    //  EVENTS
    // ─────────────────────────────────────────────────────────────────────────

    event OwnershipTransferProposed(address indexed current, address indexed proposed);
    event OwnershipTransferred(address indexed oldOwner, address indexed newOwner);
    event AgentAdded(address indexed agent, uint256 dailyLimitUsdc);
    event AgentRevoked(address indexed agent);
    event AgentLimitChanged(address indexed agent, uint256 newLimit);
    event AgentPaused(address indexed agent);
    event AgentResumed(address indexed agent);
    event Executed(address indexed agent, address indexed target, uint256 value, bytes data);
    event MultisigTxProposed(bytes32 indexed txId, address indexed proposer);
    event MultisigTxApproved(bytes32 indexed txId, address indexed signer, uint256 approvals);
    event MultisigTxReadyToExecute(bytes32 indexed txId, uint256 executeAfter);
    event MultisigTxExecuted(bytes32 indexed txId);
    event MultisigTxCancelled(bytes32 indexed txId);
    event MultisigThresholdChanged(uint256 newThreshold);
    event ExecutionDelayChanged(uint256 newDelay);
    event EtherReceived(address indexed sender, uint256 amount);

    // ─────────────────────────────────────────────────────────────────────────
    //  CONSTRUCTOR
    // ─────────────────────────────────────────────────────────────────────────

    constructor(
        address _owner,
        address[] memory _signers,
        uint256 _requiredSignatures,
        uint256 _multisigThreshold
    ) {
        require(_owner != address(0), "Invalid owner");
        require(
            _signers.length >= _requiredSignatures && _requiredSignatures > 0,
            "Invalid multisig config"
        );
        owner              = _owner;
        signers            = _signers;
        requiredSignatures = _requiredSignatures;
        multisigThreshold  = _multisigThreshold;
    }

    receive() external payable {
        emit EtherReceived(msg.sender, msg.value);
    }

    // ─────────────────────────────────────────────────────────────────────────
    //  OWNERSHIP  [FIX-5]
    // ─────────────────────────────────────────────────────────────────────────

    /** @notice Step 1 — current owner proposes a new owner. */
    function proposeOwner(address newOwner) external onlyOwner {
        require(newOwner != address(0), "Invalid address");
        pendingOwner = newOwner;
        emit OwnershipTransferProposed(owner, newOwner);
    }

    /** @notice Step 2 — proposed owner accepts and becomes the new owner. */
    function acceptOwnership() external {
        require(msg.sender == pendingOwner, "Not pending owner");
        emit OwnershipTransferred(owner, pendingOwner);
        owner        = pendingOwner;
        pendingOwner = address(0);
    }

    // ─────────────────────────────────────────────────────────────────────────
    //  AGENT MANAGEMENT
    // ─────────────────────────────────────────────────────────────────────────

    /**
     * @notice Add or update an agent with a daily USDC spending limit.
     * @param agent          Agent EOA address.
     * @param dailyLimitUsdc Daily cap in USDC (6 decimals). E.g. 500e6 = 500 USDC.
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

    /** @notice Permanently revoke an agent's access. */
    function revokeAgent(address agent) external onlyOwner {
        isAgent[agent] = false;
        agentLimits[agent].active = false;
        emit AgentRevoked(agent);
    }

    /** @notice Temporarily pause a single agent without revoking. */
    function pauseAgent(address agent) external onlyOwner {
        agentLimits[agent].active = false;
        emit AgentPaused(agent);
    }

    /** @notice Resume a paused agent. */
    function resumeAgent(address agent) external onlyOwner {
        require(isAgent[agent], "Agent not registered");
        agentLimits[agent].active = true;
        emit AgentResumed(agent);
    }

    /** @notice Update daily spending limit for an agent. */
    function setAgentLimit(address agent, uint256 newLimit) external onlyOwner {
        require(isAgent[agent], "Agent not registered");
        agentLimits[agent].dailyLimitUsdc = newLimit;
        emit AgentLimitChanged(agent, newLimit);
    }

    /** @notice Emergency: pause ALL agents instantly. */
    function pause()   external onlyOwner { _pause(); }
    function unpause() external onlyOwner { _unpause(); }

    // ─────────────────────────────────────────────────────────────────────────
    //  AGENT EXECUTION  [FIX-1]
    // ─────────────────────────────────────────────────────────────────────────

    /**
     * @notice Execute a transaction on behalf of the wallet.
     *
     *   - valueUsdc < multisigThreshold → executes immediately within daily limit.
     *   - valueUsdc >= multisigThreshold → queues a pending multisig tx.
     *
     *   [FIX-1] All agent calls go through this single entry point.
     *           Pass valueUsdc = 0 for non-financial calls — they skip budget
     *           accounting but are still gated by agent status and wallet pause.
     *
     * @param target    Contract to call.
     * @param value     ETH to send (wei).
     * @param data      ABI-encoded calldata.
     * @param valueUsdc USDC-equivalent for limit accounting (6 dec). 0 = skip.
     */
    function execute(
        address target,
        uint256 value,
        bytes calldata data,
        uint256 valueUsdc
    ) external onlyAgent whenNotPaused nonReentrant returns (bytes memory result) {

        if (multisigThreshold > 0 && valueUsdc >= multisigThreshold) {
            _proposeTx(target, value, data);
            return "";
        }

        if (valueUsdc > 0) {
            _checkAndUpdateDailyLimit(msg.sender, valueUsdc);
        }

        result = _doCall(target, value, data);
        emit Executed(msg.sender, target, value, data);
    }

    // ─────────────────────────────────────────────────────────────────────────
    //  MULTISIG FLOW
    // ─────────────────────────────────────────────────────────────────────────

    /**
     * @notice Signer approves a pending multisig tx.
     *         [FIX-3] When M approvals reached, timelock starts — NOT executed yet.
     */
    function approveTx(bytes32 txId) external onlySigner whenNotPaused {
        PendingTx storage ptx = _pendingTxs[txId];
        require(ptx.target != address(0),  "Tx does not exist");
        require(
            ptx.status == TxStatus.Pending || ptx.status == TxStatus.Approved,
            "Tx not approvable"
        );
        require(!ptx.approved[msg.sender], "Already approved");

        ptx.approved[msg.sender] = true;
        ptx.approvals++;
        emit MultisigTxApproved(txId, msg.sender, ptx.approvals);

        if (ptx.approvals >= requiredSignatures && ptx.status == TxStatus.Pending) {
            ptx.status     = TxStatus.Approved;
            ptx.approvedAt = block.timestamp;
            emit MultisigTxReadyToExecute(txId, block.timestamp + executionDelay);
        }
    }

    /**
     * @notice Execute a fully-approved multisig tx after the timelock expires.
     *         [FIX-3] Anyone can call once delay has passed.
     */
    function executeTx(bytes32 txId) external nonReentrant whenNotPaused {
        PendingTx storage ptx = _pendingTxs[txId];
        require(ptx.status == TxStatus.Approved, "Tx not fully approved");
        require(
            block.timestamp >= ptx.approvedAt + executionDelay,
            "Timelock not expired"
        );

        ptx.status = TxStatus.Executed;
        _removePendingTxId(txId); // [FIX-4]
        _doCall(ptx.target, ptx.value, ptx.data);
        emit MultisigTxExecuted(txId);
    }

    /**
     * @notice Owner cancels a pending or approved multisig tx.
     *         [FIX-4] Cleans up from pendingTxIds.
     */
    function cancelTx(bytes32 txId) external onlyOwner {
        PendingTx storage ptx = _pendingTxs[txId];
        require(ptx.target != address(0),       "Tx does not exist");
        require(ptx.status != TxStatus.Executed,  "Already executed");
        require(ptx.status != TxStatus.Cancelled, "Already cancelled");

        ptx.status = TxStatus.Cancelled;
        _removePendingTxId(txId); // [FIX-4]
        emit MultisigTxCancelled(txId);
    }

    /** @notice Update multisig spending threshold. */
    function setMultisigThreshold(uint256 newThreshold) external onlyOwner {
        multisigThreshold = newThreshold;
        emit MultisigThresholdChanged(newThreshold);
    }

    /**
     * @notice Update timelock delay (min 5 minutes, max 7 days).
     */
    function setExecutionDelay(uint256 newDelay) external onlyOwner {
        require(newDelay >= 5 minutes && newDelay <= 7 days, "Invalid delay");
        executionDelay = newDelay;
        emit ExecutionDelayChanged(newDelay);
    }

    // ─────────────────────────────────────────────────────────────────────────
    //  TOKEN HELPERS
    // ─────────────────────────────────────────────────────────────────────────

    /** @notice Withdraw ERC-20 tokens (owner only). */
    function withdrawToken(address token, uint256 amount, address to)
        external onlyOwner
    {
        IERC20(token).safeTransfer(to, amount);
    }

    /** @notice Withdraw ETH (owner only). */
    function withdrawEth(uint256 amount, address payable to)
        external onlyOwner
    {
        require(address(this).balance >= amount, "Insufficient ETH");
        (bool ok,) = to.call{value: amount}("");
        require(ok, "ETH transfer failed");
    }

    // ─────────────────────────────────────────────────────────────────────────
    //  VIEW HELPERS
    // ─────────────────────────────────────────────────────────────────────────

    /** @notice Remaining daily budget for an agent (USDC, 6 decimals). */
    function remainingDailyLimit(address agent) external view returns (uint256) {
        AgentLimit storage lim = agentLimits[agent];
        if (block.timestamp >= lim.periodStart + 1 days) {
            return lim.dailyLimitUsdc;
        }
        uint256 spent = lim.spentToday;
        return lim.dailyLimitUsdc > spent ? lim.dailyLimitUsdc - spent : 0;
    }

    /** @notice Number of active pending multisig txs. */
    function pendingTxCount() external view returns (uint256) {
        return pendingTxIds.length;
    }

    /** @notice Full status of a multisig tx. */
    function getTxStatus(bytes32 txId) external view returns (
        TxStatus status,
        uint256  approvals,
        uint256  approvedAt,
        uint256  executeAfter
    ) {
        PendingTx storage ptx = _pendingTxs[txId];
        status       = ptx.status;
        approvals    = ptx.approvals;
        approvedAt   = ptx.approvedAt;
        executeAfter = ptx.approvedAt > 0 ? ptx.approvedAt + executionDelay : 0;
    }

    /** @notice Whether a signer has approved a specific tx. */
    function hasApproved(bytes32 txId, address signer) external view returns (bool) {
        return _pendingTxs[txId].approved[signer];
    }

    // ─────────────────────────────────────────────────────────────────────────
    //  INTERNAL HELPERS
    // ─────────────────────────────────────────────────────────────────────────

    function _checkAndUpdateDailyLimit(address agent, uint256 valueUsdc) internal {
        AgentLimit storage lim = agentLimits[agent];
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

    /** @dev [FIX-2] Uses _nonce for unique txId per proposal. */
    function _proposeTx(address target, uint256 value, bytes calldata data) internal {
        bytes32 txId = keccak256(
            abi.encode(target, value, data, block.timestamp, msg.sender, _nonce++)
        );
        PendingTx storage ptx = _pendingTxs[txId];
        ptx.target = target;
        ptx.value  = value;
        ptx.data   = data;
        ptx.status = TxStatus.Pending;

        _txIdIndex[txId] = pendingTxIds.length;
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

    /** @dev [FIX-4] O(1) removal via swap-and-pop. */
    function _removePendingTxId(bytes32 txId) internal {
        uint256 idx  = _txIdIndex[txId];
        uint256 last = pendingTxIds.length - 1;
        if (idx != last) {
            bytes32 lastId     = pendingTxIds[last];
            pendingTxIds[idx]  = lastId;
            _txIdIndex[lastId] = idx;
        }
        pendingTxIds.pop();
        delete _txIdIndex[txId];
    }
}
