"""
FaceFlow AI — Blockchain Service
Abstract registry interface + Ethereum Sepolia implementation via Web3.py.
"""

from __future__ import annotations

import abc
import json
import time
from typing import Optional

from app.core.config import settings
from app.core.logging import get_logger
from app.models.schemas import BlockchainRecord
from app.utils.canonical_json import fingerprint_to_bytes32

logger = get_logger(__name__)

# ── Minimal ABI for ContentRegistry contract ─────────────────
CONTENT_REGISTRY_ABI = json.loads("""
[
  {
    "inputs": [{"internalType": "bytes32", "name": "fingerprint", "type": "bytes32"}],
    "name": "register",
    "outputs": [],
    "stateMutability": "nonpayable",
    "type": "function"
  },
  {
    "inputs": [{"internalType": "bytes32", "name": "fingerprint", "type": "bytes32"}],
    "name": "verify",
    "outputs": [
      {"internalType": "bool", "name": "", "type": "bool"},
      {"internalType": "uint256", "name": "", "type": "uint256"}
    ],
    "stateMutability": "view",
    "type": "function"
  },
  {
    "inputs": [{"internalType": "bytes32", "name": "", "type": "bytes32"}],
    "name": "registeredAt",
    "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
    "stateMutability": "view",
    "type": "function"
  },
  {
    "anonymous": false,
    "inputs": [
      {"indexed": true, "internalType": "bytes32", "name": "fingerprint", "type": "bytes32"},
      {"indexed": false, "internalType": "uint256", "name": "timestamp", "type": "uint256"},
      {"indexed": true, "internalType": "address", "name": "submitter", "type": "address"}
    ],
    "name": "ContentRegistered",
    "type": "event"
  }
]
""")


# ── Abstract base ────────────────────────────────────────────

class BlockchainRegistry(abc.ABC):
    @abc.abstractmethod
    async def register(self, fingerprint_hex: str) -> BlockchainRecord:
        """Write fingerprint to blockchain. Returns transaction record."""
        ...

    @abc.abstractmethod
    async def get_registered_fingerprint(self, tx_hash: str) -> Optional[str]:
        """
        Look up a transaction and return the fingerprint stored in it.
        Returns None if TX not found or cannot be decoded.
        """
        ...

    @abc.abstractmethod
    async def is_registered(self, fingerprint_hex: str) -> tuple[bool, Optional[int]]:
        """
        Check if a fingerprint is registered on-chain.
        Returns (is_registered, timestamp_unix_or_None).
        """
        ...

    async def health_check(self) -> bool:
        return True


# ── Ethereum Sepolia implementation ──────────────────────────

class EthereumSepoliaRegistry(BlockchainRegistry):

    def __init__(self) -> None:
        self._w3 = None
        self._contract = None
        self._account = None

    def _get_web3(self):
        """Lazy-initialize Web3 connection."""
        if self._w3 is None:
            from web3 import Web3

            self._w3 = Web3(Web3.HTTPProvider(settings.sepolia_rpc_url))

            # Inject PoA middleware (optional — Sepolia is PoS but some
            # providers include extra data fields that need this shim)
            try:
                from web3.middleware import ExtraDataToPOAMiddleware
                self._w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
            except Exception:
                pass  # Not required on Sepolia; ignore if unavailable

            if not self._w3.is_connected():
                raise RuntimeError("BLOCKCHAIN_RPC_ERROR: Cannot connect to Sepolia RPC")

            logger.info("Web3 connected. Chain ID: %s", self._w3.eth.chain_id)

        return self._w3

    def _get_account(self):
        """Lazy-load account from private key."""
        if self._account is None:
            w3 = self._get_web3()
            self._account = w3.eth.account.from_key(settings.blockchain_private_key)
            logger.info("Wallet address: %s", self._account.address)
        return self._account

    def _get_contract(self):
        """Lazy-load contract instance."""
        if self._contract is None:
            from web3 import Web3
            w3 = self._get_web3()
            if not settings.contract_address:
                raise RuntimeError("BLOCKCHAIN_RPC_ERROR: CONTRACT_ADDRESS not configured")
            self._contract = w3.eth.contract(
                address=Web3.to_checksum_address(settings.contract_address),
                abi=CONTENT_REGISTRY_ABI,
            )
        return self._contract

    async def register(self, fingerprint_hex: str) -> BlockchainRecord:
        """Build, sign and send a register() transaction on Sepolia."""
        if not settings.blockchain_configured:
            raise RuntimeError("BLOCKCHAIN_RPC_ERROR: Blockchain not configured")

        w3 = self._get_web3()
        account = self._get_account()
        contract = self._get_contract()

        fp_bytes = fingerprint_to_bytes32(fingerprint_hex)

        # Build transaction
        nonce = w3.eth.get_transaction_count(account.address)
        gas_price = w3.eth.gas_price

        tx = contract.functions.register(fp_bytes).build_transaction({
            "chainId": settings.chain_id,
            "gas": 100000,
            "gasPrice": gas_price,
            "nonce": nonce,
        })

        # Sign & send
        signed = account.sign_transaction(tx)
        tx_hash_bytes = w3.eth.send_raw_transaction(signed.raw_transaction)
        tx_hash = tx_hash_bytes.hex()
        if not tx_hash.startswith("0x"):
            tx_hash = "0x" + tx_hash

        logger.info("Transaction sent: %s", tx_hash)

        # Wait for confirmation
        receipt = w3.eth.wait_for_transaction_receipt(
            tx_hash_bytes,
            timeout=120,
            poll_latency=3,
        )

        confirmed = receipt.status == 1
        block_number = receipt.blockNumber

        logger.info(
            "TX confirmed: block=%d status=%s", block_number, "SUCCESS" if confirmed else "FAILED"
        )

        return BlockchainRecord(
            network="Ethereum Sepolia",
            chain_id=settings.chain_id,
            transaction_hash=tx_hash,
            fingerprint=fingerprint_hex,
            confirmed=confirmed,
            block_number=block_number,
            registered_at=int(time.time()),
        )

    async def get_registered_fingerprint(self, tx_hash: str) -> Optional[str]:
        """Decode the fingerprint bytes32 from a register() transaction's input data."""
        try:
            w3 = self._get_web3()
            contract = self._get_contract()

            tx = w3.eth.get_transaction(tx_hash)
            if tx is None:
                logger.warning("TX not found: %s", tx_hash)
                return None

            # Decode input
            _, decoded = contract.decode_function_input(tx["input"])
            fp_bytes: bytes = decoded.get("fingerprint", b"")
            if not fp_bytes:
                return None

            return fp_bytes.hex()
        except Exception as e:
            logger.error("Error decoding TX %s: %s", tx_hash, e)
            return None

    async def is_registered(self, fingerprint_hex: str) -> tuple[bool, Optional[int]]:
        """Call contract.verify() view function."""
        try:
            contract = self._get_contract()
            fp_bytes = fingerprint_to_bytes32(fingerprint_hex)
            found, timestamp = contract.functions.verify(fp_bytes).call()
            return found, (int(timestamp) if found else None)
        except Exception as e:
            logger.error("Error checking registration for %s: %s", fingerprint_hex[:16], e)
            return False, None

    async def health_check(self) -> bool:
        try:
            w3 = self._get_web3()
            return w3.is_connected()
        except Exception:
            return False


# ── Singleton ────────────────────────────────────────────────
_registry: BlockchainRegistry | None = None


def get_blockchain_registry() -> BlockchainRegistry:
    global _registry
    if _registry is None:
        _registry = EthereumSepoliaRegistry()
    return _registry
