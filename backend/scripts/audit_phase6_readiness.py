"""
WAPSI Phase 6 Readiness Integration Audit Script.
Verifies all 7 provider test-mode components and state machines.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import hmac
import hashlib
from decimal import Decimal

print("=== PHASE 6 READINESS VERIFICATION AUDIT ===")

# 1. Razorpay Test Mode Client & Webhook Signature Verification
from wapsi.integrations.razorpay.client import RazorpayClient
from wapsi.integrations.razorpay.webhook import RazorpayWebhookHandler

rzp = RazorpayClient(key_id="rzp_test_demo123", key_secret="dummy_secret_123")
print("1. RazorpayClient initialized with Test Mode prefix:", rzp.key_id.startswith("rzp_test_"))
assert rzp.key_id.startswith("rzp_test_")

raw_body = b'{"event":"payment.captured","payload":{"payment":{"entity":{"id":"pay_123"}}}}'
secret = b"test_webhook_secret_xyz"
sig = hmac.new(secret, raw_body, hashlib.sha256).hexdigest()
is_valid_rzp_sig = RazorpayWebhookHandler.verify_signature(raw_body=raw_body, signature=sig, secret=secret)
print("   Razorpay webhook signature verification:", is_valid_rzp_sig)
assert is_valid_rzp_sig is True

# 2. WhatsApp Cloud API Client & Webhook Signature Verification
from wapsi.integrations.whatsapp.client import WhatsAppClient
from wapsi.integrations.whatsapp.webhook import WhatsAppWebhookHandler

wa = WhatsAppClient(access_token="dummy_access_token", phone_number_id="10987654321")
print("2. WhatsAppClient initialized:", bool(wa))

wa_body = b'{"object":"whatsapp_business_account","entry":[]}'
wa_sig = "sha256=" + hmac.new(b"meta_app_secret_123", wa_body, hashlib.sha256).hexdigest()
is_valid_wa_sig = WhatsAppWebhookHandler.verify_signature(raw_body=wa_body, signature_header=wa_sig, app_secret="meta_app_secret_123")
print("   WhatsApp webhook signature verification:", is_valid_wa_sig)
assert is_valid_wa_sig is True

# 3. Durable Outbox & Webhook Inbox
from wapsi.recovery.outbox import DurableOutboxStore
from wapsi.recovery.webhook_processor import DurableWebhookInbox

outbox = DurableOutboxStore(db_path=":memory:")
inbox = DurableWebhookInbox(db_path=":memory:")
print("3. Durable outbox and webhook inbox initialized.")

# 4. Persistent Customer Opt-Out Enforcement
from wapsi.recovery.opt_out_store import PersistentOptOutStore
import tempfile, os

temp_opt_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False).name
try:
    opt_out = PersistentOptOutStore(db_path=temp_opt_db)
    opt_out.record_opt_out("+919876543210", source="WHATSAPP_STOP")
    is_opted = opt_out.is_opted_out("+919876543210")
    print("4. Persistent opt-out check (+919876543210):", is_opted)
    assert is_opted is True
finally:
    if os.path.exists(temp_opt_db):
        try:
            os.remove(temp_opt_db)
        except Exception:
            pass

# 5. Case-to-Payment and Case-to-Message Mapping
from wapsi.recovery.webhook_processor import DurableWebhookEventProcessor

proc = DurableWebhookEventProcessor(inbox=inbox, outbox_store=outbox)
proc.register_case_mapping(
    case_id="RX-TEST01",
    payment_link_id="plink_test_999",
    whatsapp_message_id="wamid_test_123",
    customer_phone="+919876543210",
)
resolved_by_link = proc._link_to_case.get("plink_test_999")
resolved_by_msg = proc._message_to_case.get("wamid_test_123")
print("5. Case mapping resolution by link:", resolved_by_link == "RX-TEST01")
print("   Case mapping resolution by message:", resolved_by_msg == "RX-TEST01")
assert resolved_by_link == "RX-TEST01"
assert resolved_by_msg == "RX-TEST01"

# 6. Recovery State Machine & Transitions
from wapsi.recovery.state_machine import RecoveryStateMachine, RecoveryState

state = RecoveryState.PENDING
state, _ = RecoveryStateMachine.transition("RX-TEST01", state, RecoveryState.ELIGIBLE, "Eligibility confirmed")
state, _ = RecoveryStateMachine.transition("RX-TEST01", state, RecoveryState.SCHEDULED, "Scheduled in outbox")
state, _ = RecoveryStateMachine.transition("RX-TEST01", state, RecoveryState.DISPATCHING, "Claimed by worker")
state, _ = RecoveryStateMachine.transition("RX-TEST01", state, RecoveryState.DISPATCHED, "Dispatched via WhatsApp")
state, _ = RecoveryStateMachine.transition("RX-TEST01", state, RecoveryState.RECOVERED, "Payment captured", is_payment_capture=True)
print("6. State machine progression valid. Final state:", state.value)
assert state == RecoveryState.RECOVERED

# 7. Payment Reconciliation Engine
from wapsi.recovery.reconciliation import PaymentReconciliationEngine

reconciler = PaymentReconciliationEngine(razorpay_client=rzp, outbox_store=outbox)
rec_res = reconciler.reconcile_case(
    case_id="RX-TEST01",
    payment_id="pay_999",
    current_state=RecoveryState.RECOVERED,
)
print("7. Payment reconciliation status:", rec_res.resulting_state)
assert rec_res.is_recovered is True
assert rec_res.resulting_state == "RECOVERED"

print("\nALL 7 PHASE 6 READINESS GATES VERIFIED SUCCESSFULLY!")
