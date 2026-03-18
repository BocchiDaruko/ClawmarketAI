# Contributing to clawmarketAI

Thank you for your interest in contributing! Here's how to get started.

## Development Setup

```bash
git clone https://github.com/your-org/clawmarketAI.git
cd clawmarketAI
npm install
pip install -r requirements.txt
cp .env.example .env
```

## Running Tests

```bash
# Smart contract tests
npm run contracts:test

# Agent unit tests
pytest tests/

# Full integration test
npm run test:integration
```

## Code Style

- Solidity: follow the [Solidity Style Guide](https://docs.soliditylang.org/en/latest/style-guide.html)
- Python: Black formatter, type hints required
- TypeScript: ESLint + Prettier

## Submitting a Pull Request

1. Fork the repository
2. Create a branch: `git checkout -b feature/your-feature`
3. Make your changes and add tests
4. Run the full test suite
5. Open a PR with a clear description of what you changed and why

## Reporting Issues

Open a GitHub issue with a clear title, steps to reproduce, expected vs actual behavior, and environment details.

## Code of Conduct

Be respectful, constructive, and collaborative. We're building an open ecosystem together.
