# FaceFlow AI

A locally-runnable Phase 1 prototype that proves the complete pipeline:

**Face Scan → Face Embedding → Google Lens Search → Candidate Face Matching → SHA-256 Fingerprint → Ethereum Sepolia Registration → Independent Blockchain Verification**

## Architecture

```
Browser
  │  POST /api/scan
  ▼
FastAPI
  ├── InsightFace     (detect face, generate ArcFace embedding)
  ├── SerpApi Lens    (reverse-image search → candidate URLs)
  ├── Candidate svc   (download → detect face → cosine similarity)
  ├── Fingerprint svc (canonical JSON → SHA-256)
  └── Blockchain svc  (Web3.py → Ethereum Sepolia → verify)
```

## Requirements

- Python 3.11+
- Accounts/keys (see Environment Variables below):
  - [SerpApi](https://serpapi.com) — free tier: 250 searches/month
  - [Alchemy](https://dashboard.alchemy.com) — free Sepolia RPC
  - Ethereum wallet with Sepolia test ETH ([Alchemy faucet](https://www.alchemy.com/faucets/ethereum-sepolia))
  - Deployed `ContentRegistry` contract address (see Blockchain section)

## Setup

```bash
# 1. Create virtual environment
python -m venv .venv

# 2. Activate (Windows)
.venv\Scripts\activate
# (Linux/Mac)
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Copy env template
copy .env.example .env      # Windows
# cp .env.example .env      # Linux/Mac

# 5. Fill in .env with your API keys (see below)
```

## Environment Variables

| Variable                      | Description                                |
| ----------------------------- | ------------------------------------------ |
| `SERPAPI_API_KEY`             | SerpApi key for Google Lens search         |
| `ALCHEMY_API_KEY`             | Alchemy key for Sepolia RPC                |
| `SEPOLIA_RPC_URL`             | Full Alchemy Sepolia RPC URL               |
| `BLOCKCHAIN_PRIVATE_KEY`      | Wallet private key (Sepolia test ETH only) |
| `CONTRACT_ADDRESS`            | Deployed ContentRegistry address           |
| `FACE_MATCH_THRESHOLD`        | Cosine similarity floor (default: `0.60`)  |
| `FACE_STRONG_MATCH_THRESHOLD` | Strong match label floor (default: `0.75`) |

## Blockchain — Deploy the Smart Contract

1. Open [Remix IDE](https://remix.ethereum.org)
2. Create a new file, paste `contracts/ContentRegistry.sol`
3. Compile with Solidity **0.8.20**
4. In Deploy tab: Environment → **Injected Provider (MetaMask)**
5. Switch MetaMask to **Sepolia** testnet
6. Click **Deploy**
7. Copy the deployed contract address
8. Paste it into `.env` as `CONTRACT_ADDRESS`

> One deployment is sufficient. The contract stores fingerprints permanently.

## Running

```bash
python run.py
```

Open `http://localhost:8000`

The InsightFace model (`buffalo_l`, ~300 MB) downloads automatically on first run.

## Running Tests

```bash
pytest tests/ -v
```

Tests cover fingerprint determinism, canonicalization, and verification logic (mocked blockchain, no API keys required).

## Verification Flow

```
Canonical record  →  SHA-256  →  Fingerprint
                                      │
                                  On-chain (Sepolia)
                                      │
                  Re-hash same record →  Compare
                                      │
                            VERIFIED / NOT VERIFIED
```

## Tampering Demo

After a successful scan, the **Tampering Test** panel lets you modify any record field (title, URL, similarity) and click **Verify Again**. The fingerprint will not match the blockchain record, demonstrating tamper-evidence.

## Limitations

- Search results depend on SerpApi / Google Lens and may vary
- Some candidate pages block direct image retrieval
- Face similarity is **not** proof of legal/real-world identity
- Sepolia is a testnet; no real ETH is used or required
- Public web results may change or disappear over time
- SerpApi free tier: 250 searches/month

## Search

Google Lens reverse-image search via SerpApi. Free tier: 250 searches/month.

## Blockchain

**Ethereum Sepolia testnet** · Chain ID: `11155111`

Fingerprints are registered via `ContentRegistry.register(bytes32)` and verified via `ContentRegistry.verify(bytes32)`. The contract reverts if a fingerprint is submitted twice, ensuring immutability.
