require("@nomicfoundation/hardhat-toolbox");
require("dotenv").config();

/** @type import('hardhat/config').HardhatUserConfig */
module.exports = {
  // ─── Solidity ───────────────────────────────────────────────────────────────
  solidity: {
    version: "0.8.24",
    settings: {
      optimizer: {
        enabled: true,
        runs: 200,
      },
      viaIR: true, // required for large contracts (Marketplace, SmartWallet)
    },
  },

  // ─── Networks ───────────────────────────────────────────────────────────────
  networks: {
    // ── Base Mainnet ───────────────────────────────────────────────────────────
    base: {
      url:     process.env.BASE_RPC_URL || "https://mainnet.base.org",
      chainId: 8453,
      accounts: process.env.DEPLOYER_PRIVATE_KEY
        ? [process.env.DEPLOYER_PRIVATE_KEY]
        : [],
      // [FIX-2] EIP-1559 config — Base L2 is fast and cheap
      // Adjust maxFeePerGas if Base is congested at deploy time
      // Leave as "auto" for local testing; set explicit values for mainnet
      gasPrice: "auto",
      timeout:  120_000, // [FIX-3] 2 min timeout for mainnet deploys
    },

    // ── Base Sepolia (testnet) ─────────────────────────────────────────────────
    baseSepolia: {
      url:     process.env.BASE_SEPOLIA_RPC_URL || "https://sepolia.base.org",
      chainId: 84532,
      accounts: process.env.DEPLOYER_PRIVATE_KEY
        ? [process.env.DEPLOYER_PRIVATE_KEY]
        : [],
      gasPrice: "auto",
      timeout:  120_000, // [FIX-3]
    },

    // ── Local Hardhat node (forks Base mainnet if BASE_RPC_URL is set) ─────────
    hardhat: {
      chainId: 31337,
      forking: process.env.BASE_RPC_URL
        ? {
            url:         process.env.BASE_RPC_URL,
            blockNumber: undefined, // latest — pin a specific block for stable tests
          }
        : undefined,
      // Simulate Base gas costs locally
      gas:      "auto",
      gasPrice: "auto",
    },
  },

  // ─── Contract verification ──────────────────────────────────────────────────
  etherscan: {
    apiKey: {
      base:        process.env.BASESCAN_API_KEY || "",
      baseSepolia: process.env.BASESCAN_API_KEY || "",
    },
    customChains: [
      {
        network: "base",
        chainId: 8453,
        urls: {
          apiURL:     "https://api.basescan.org/api",
          browserURL: "https://basescan.org",
        },
      },
      {
        network: "baseSepolia",
        chainId: 84532,
        urls: {
          apiURL:     "https://api-sepolia.basescan.org/api",
          browserURL: "https://sepolia.basescan.org",
        },
      },
    ],
  },

  // [FIX-1] Sourcify — fallback verifier if Basescan is down or slow
  sourcify: {
    enabled: true,
  },

  // ─── Gas reporter ───────────────────────────────────────────────────────────
  gasReporter: {
    enabled:      process.env.REPORT_GAS === "true",
    currency:     "USD",
    token:        "ETH",
    gasPriceApi:  "https://api.basescan.org/api?module=proxy&action=eth_gasPrice",
    outputFile:   process.env.REPORT_GAS === "true" ? "gas-report.txt" : undefined,
    noColors:     process.env.REPORT_GAS === "true",
  },

  // ─── Named accounts [FIX-4] ─────────────────────────────────────────────────
  // Used in deploy scripts: const { deployer } = await getNamedAccounts()
  namedAccounts: {
    deployer: {
      default: 0, // first account from DEPLOYER_PRIVATE_KEY
    },
    feeWallet: {
      default: 1, // second account — override in .env for mainnet
    },
  },

  // ─── Paths ──────────────────────────────────────────────────────────────────
  paths: {
    sources:   "./contracts",
    tests:     "./tests",
    cache:     "./cache",
    artifacts: "./artifacts",
  },

  // ─── Mocha (test runner) ────────────────────────────────────────────────────
  mocha: {
    timeout: 120_000, // 2 min per test — important for forked network tests
  },
};
