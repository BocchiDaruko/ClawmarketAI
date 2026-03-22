// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import "@openzeppelin/contracts/access/Ownable.sol";

/**
 * @title  MockERC20
 * @notice Simple mintable ERC20 for testnet deployments only.
 *         NOT for production use.
 */
contract MockERC20 is ERC20, Ownable {
    uint8 private _decimals;

    constructor(
        string memory name,
        string memory symbol,
        uint8 decimals_
    ) ERC20(name, symbol) Ownable(msg.sender) {
        _decimals = decimals_;
        // Mint 1,000,000 tokens to deployer for testing
        _mint(msg.sender, 1_000_000 * (10 ** decimals_));
    }

    function decimals() public view override returns (uint8) {
        return _decimals;
    }

    /// @notice Anyone can mint on testnet — for testing only
    function mint(address to, uint256 amount) external {
        _mint(to, amount);
    }
}
