"""
Cryptographically Verifiable Append-Only Audit Ledger.
Chains every recovery decision, policy check, dispatch receipt, and outcome via SHA-256 hashes.
"""

from typing import Dict, List, Any, Optional
import hashlib
import json
from datetime import datetime, timezone


class AuditLedgerBlock:
    def __init__(
        self,
        index: int,
        timestamp: str,
        event_type: str,
        data: Dict[str, Any],
        prev_hash: str
    ):
        self.index = index
        self.timestamp = timestamp
        self.event_type = event_type
        self.data = data
        self.prev_hash = prev_hash
        self.block_hash = self.compute_hash()

    def compute_hash(self) -> str:
        payload_str = json.dumps({
            "index": self.index,
            "timestamp": self.timestamp,
            "event_type": self.event_type,
            "data": self.data,
            "prev_hash": self.prev_hash
        }, sort_keys=True)
        return hashlib.sha256(payload_str.encode("utf-8")).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "index": self.index,
            "timestamp": self.timestamp,
            "event_type": self.event_type,
            "data": self.data,
            "prev_hash": self.prev_hash,
            "block_hash": self.block_hash
        }


class AuditLedger:
    """
    Tamper-evident append-only audit ledger for regulatory compliance and dispute resolution.
    """

    def __init__(self):
        self.chain: List[AuditLedgerBlock] = []
        self._create_genesis_block()

    def _create_genesis_block(self):
        genesis = AuditLedgerBlock(
            index=0,
            timestamp="2026-01-01T00:00:00Z",
            event_type="GENESIS",
            data={"system": "WAPSI Razorpay Recovery Router Audit Ledger v1.0"},
            prev_hash="0" * 64
        )
        self.chain.append(genesis)

    def append(self, event_type: str, data: Dict[str, Any]) -> AuditLedgerBlock:
        """
        Appends a new event block chained to the latest block hash.
        """
        prev_block = self.chain[-1]
        now_iso = datetime.now(timezone.utc).isoformat()
        
        # Deepcopy or sanitize data to ensure JSON serialization
        safe_data = json.loads(json.dumps(data, default=str))

        new_block = AuditLedgerBlock(
            index=len(self.chain),
            timestamp=now_iso,
            event_type=event_type,
            data=safe_data,
            prev_hash=prev_block.block_hash
        )
        self.chain.append(new_block)
        return new_block

    def verify_integrity(self) -> Dict[str, Any]:
        """
        Validates cryptographic integrity of all blocks in the ledger chain.
        """
        for i in range(1, len(self.chain)):
            curr = self.chain[i]
            prev = self.chain[i - 1]

            # Verify prev_hash link
            if curr.prev_hash != prev.block_hash:
                return {
                    "is_valid": False,
                    "error": f"Broken chain link at block index {i}: prev_hash mismatch",
                    "corrupted_block_index": i
                }

            # Verify current hash computation
            recalculated = curr.compute_hash()
            if curr.block_hash != recalculated:
                return {
                    "is_valid": False,
                    "error": f"Tampered data at block index {i}: computed hash does not match stored block_hash",
                    "corrupted_block_index": i
                }

        return {
            "is_valid": True,
            "total_blocks": len(self.chain),
            "latest_block_hash": self.chain[-1].block_hash
        }

    def get_entries(self, limit: int = 50) -> List[Dict[str, Any]]:
        entries = [b.to_dict() for b in self.chain]
        entries.reverse()
        return entries[:limit]
