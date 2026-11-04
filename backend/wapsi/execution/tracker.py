"""
Promise-to-Pay & Recovery Outcome Tracker.
Maintains payment state machine, processes gateway webhooks, and closes the learning loop.
"""

from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from wapsi.core.taxonomy import RecoveryStatus


class RecoveryOutcomeTracker:
    """
    Tracks lifecycle states of all recovery interventions.
    """

    def __init__(self):
        # payment_id -> state record
        self.recovery_records: Dict[str, Dict[str, Any]] = {}

    def initialize_record(
        self,
        payment_id: str,
        decision_id: str,
        dispatch_id: str,
        action: str,
        amount_in_inr: float,
        merchant_id: str
    ) -> Dict[str, Any]:
        """
        Initializes a recovery tracking record upon dispatch.
        """
        now_iso = datetime.now(timezone.utc).isoformat()
        record = {
            "payment_id": payment_id,
            "decision_id": decision_id,
            "dispatch_id": dispatch_id,
            "action": action,
            "merchant_id": merchant_id,
            "amount_in_inr": amount_in_inr,
            "status": RecoveryStatus.DISPATCHED.value,
            "created_at": now_iso,
            "updated_at": now_iso,
            "history": [
                {"status": RecoveryStatus.DISPATCHED.value, "timestamp": now_iso, "note": f"Action {action} dispatched"}
            ]
        }
        self.recovery_records[payment_id] = record
        return record

    def update_status(
        self,
        payment_id: str,
        new_status: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Transitions payment recovery status based on gateway callbacks.
        """
        if payment_id not in self.recovery_records:
            # Create stub if not tracked prior
            self.recovery_records[payment_id] = {
                "payment_id": payment_id,
                "status": new_status,
                "amount_in_inr": metadata.get("amount_in_inr", 1000.0) if metadata else 1000.0,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "history": []
            }

        record = self.recovery_records[payment_id]
        now_iso = datetime.now(timezone.utc).isoformat()
        record["status"] = new_status
        record["updated_at"] = now_iso
        record["history"].append({
            "status": new_status,
            "timestamp": now_iso,
            "metadata": metadata or {}
        })

        return record

    def get_record(self, payment_id: str) -> Optional[Dict[str, Any]]:
        return self.recovery_records.get(payment_id)

    def list_all(self, limit: int = 50) -> List[Dict[str, Any]]:
        records = list(self.recovery_records.values())
        records.reverse()
        return records[:limit]
