require("@nomicfoundation/hardhat-toolbox");
require("dotenv").config();

/** @type import('hardhat/config').HardhatUserConfig */
module.exports = {
  solidity: {
    version: "0.8.24",
    settings: {
      optimizer: {
        enabled: true,
        runs: 200,
      },
      viaIR: true,
    },
  },

  networks: {
    // ── Base Mainnet ──────────────────────────────────────────────────────────
    base: {
      url:      process.env.BASE_RPC_URL || "https://mainnet.base.org",
      chainId:  8453,
      accounts: process.env.DEPLOYER_PRIVATE_KEY
        ? [process.env.DEPLOYER_PRIVATE_KEY]
        : [],
      gasPrice: "auto",
    },

    // ── Base Sepolia (testnet) ────────────────────────────────────────────────
    baseSepolia: {
      url:      process.env.BASE_SEPOLIA_RPC_URL || "https://sepolia.base.org",
      chainId:  84532,
      accounts: process.env.DEPLOYER_PRIVATE_KEY
        ? [process.env.DEPLOYER_PRIVATE_KEY]
        : [],
      gasPrice: "auto",
    },

    // ── Local hardhat node ────────────────────────────────────────────────────
    hardhat: {
      chainId: 31337,
      forking: process.env.BASE_RPC_URL ? {
        url:         process.env.BASE_RPC_URL,
        blockNumber: undefined, // latest
      } : undefined,
    },
  },

  etherscan: {
    apiKey: {
      base:        process.env.BASESCAN_API_KEY || "",
      baseSepolia: process.env.BASESCAN_API_KEY || "",
    },
    customChains: [
      {
        network:  "base",
        chainId:  8453,
        urls: {
          apiURL:     "https://api.basescan.org/api",
          browserURL: "https://basescan.org",
        },
      },
      {
        network:  "baseSepolia",
        chainId:  84532,
        urls: {
          apiURL:     "https://api-sepolia.basescan.org/api",
          browserURL: "https://sepolia.basescan.org",
        },
      },
    ],
  },

  gasReporter: {
    enabled:     process.env.REPORT_GAS === "true",
    currency:    "USD",
    token:       "ETH",
    gasPriceApi: "https://api.basescan.org/api?module=proxy&action=eth_gasPrice",
  },

  paths: {
    sources:   "./contracts",
    tests:     "./tests",
    cache:     "./cache",
    artifacts: "./artifacts",
  },
};
