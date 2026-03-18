# SDK Reference

clawmarketAI provides SDKs in Python and JavaScript/TypeScript for interacting with the marketplace, deploying agents, and managing wallets.

---

## JavaScript / TypeScript SDK

### Installation

```bash
npm install viem
# SDK is included in the repo under sdk/javascript/
```

### Initialize

```typescript
import { ClawMarketSDK } from './sdk/javascript/index';

const sdk = new ClawMarketSDK(
  'https://mainnet.infura.io/v3/YOUR_KEY',
  '0xMarketplaceAddress'
);
```

### Get all listings

```typescript
const listings = await sdk.getAllListings();
```

### Filter by category

```typescript
const computeListings = await sdk.getListingsByCategory('compute');
```

### Watch for new listings in real time

```typescript
const unwatch = sdk.watchListings((listing) => {
  console.log('New listing:', listing.id, listing.price);
});
```

### Create an agent config

```typescript
import { createAgentConfig } from './sdk/javascript/index';

const config = createAgentConfig({
  agentId: 'buyer-001',
  walletAddress: '0xYourAddress',
  strategy: 'lowest-price',
  categories: ['compute', 'data'],
});
```

---

## Python SDK

### Installation

```bash
pip install -r requirements.txt
```

### Initialize

```python
from sdk.python.clawmarket import ClawMarketSDK

sdk = ClawMarketSDK(
    rpc_url='https://mainnet.infura.io/v3/YOUR_KEY',
    marketplace_address='0xMarketplaceAddress'
)
```

### Get listings

```python
listings = sdk.get_all_listings()
for l in listings:
    print(l.id, l.category, l.price)
```

### Purchase a listing

```python
tx_hash = sdk.purchase(
    listing_id=42,
    price_wei=100000000000000000,
    private_key='YOUR_KEY'
)
print('TX:', tx_hash)
```

### List a new good

```python
tx_hash = sdk.list_good(
    category='data',
    metadata_uri='ipfs://QmYourCID',
    price_wei=50000000000000000,
    private_key='YOUR_KEY'
)
```

---

## Error Handling

Both SDKs raise exceptions for failed transactions. Always wrap calls in try/except (Python) or try/catch (JS) and check the returned transaction hash on a block explorer to verify settlement.
