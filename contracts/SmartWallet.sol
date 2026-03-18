// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @title clawmarketAI SmartWallet
/// @notice Agent-controlled wallet with spending limits and permissions
contract SmartWallet {

    address public owner;
    mapping(address => bool) public authorizedAgents;
    mapping(address => uint256) public agentSpendLimit;   // per-tx limit in wei
    mapping(address => uint256) public agentSpentToday;
    mapping(address => uint256) public lastResetTimestamp;

    uint256 public constant DAY = 86400;

    event AgentAuthorized(address indexed agent, uint256 spendLimit);
    event AgentRevoked(address indexed agent);
    event TransactionExecuted(address indexed agent, address to, uint256 value);

    modifier onlyOwner() {
        require(msg.sender == owner, "Not owner");
        _;
    }

    modifier onlyAuthorized() {
        require(authorizedAgents[msg.sender], "Not authorized agent");
        _;
    }

    constructor() {
        owner = msg.sender;
    }

    receive() external payable {}

    /// @notice Authorize an AI agent with a daily spend cap
    function authorizeAgent(address agent, uint256 dailyLimit) external onlyOwner {
        authorizedAgents[agent] = true;
        agentSpendLimit[agent] = dailyLimit;
        emit AgentAuthorized(agent, dailyLimit);
    }

    /// @notice Revoke an agent's access
    function revokeAgent(address agent) external onlyOwner {
        authorizedAgents[agent] = false;
        emit AgentRevoked(agent);
    }

    /// @notice Agent executes a transaction within its spend limit
    function execute(address to, uint256 value, bytes calldata data)
        external
        onlyAuthorized
        returns (bytes memory)
    {
        _resetIfNewDay(msg.sender);
        require(
            agentSpentToday[msg.sender] + value <= agentSpendLimit[msg.sender],
            "Daily spend limit exceeded"
        );

        agentSpentToday[msg.sender] += value;

        (bool success, bytes memory result) = to.call{value: value}(data);
        require(success, "Transaction failed");

        emit TransactionExecuted(msg.sender, to, value);
        return result;
    }

    function _resetIfNewDay(address agent) internal {
        if (block.timestamp >= lastResetTimestamp[agent] + DAY) {
            agentSpentToday[agent] = 0;
            lastResetTimestamp[agent] = block.timestamp;
        }
    }

    function getBalance() external view returns (uint256) {
        return address(this).balance;
    }
}
