import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import sqlite3
import json
from wapsi.db.session import DatabaseManager
from sqlalchemy import text

TARGET_WAMID = "wamid.HBgMOTE2MjYwMDU1NjcxFQIAEhggQTVBQjRBNEU4NTk3NEI2RjVFMjQ1Njc4QTVDNzg5QjQA"
TARGET_TS = 1793637318

print("=== 1. POSTGRESQL INSPECTION ===")
dm = DatabaseManager()
with dm.session_scope() as session:
    # Check webhook_inbox
    rows = session.execute(text("SELECT * FROM webhook_inbox WHERE event_id LIKE :w OR payment_id LIKE :w"), {"w": f"%{TARGET_WAMID}%"}).fetchall()
    print(f"PostgreSQL webhook_inbox matches for WAMID: {len(rows)}")
    for r in rows:
        print(" ", dict(r._mapping))
    
    # Check customer_interactions
    ci_rows = session.execute(text("SELECT * FROM customer_interactions")).fetchall()
    print(f"PostgreSQL customer_interactions rows: {len(ci_rows)}")
    for r in ci_rows:
        print(" ", dict(r._mapping))

    # Check opt_out_registry
    oor_rows = session.execute(text("SELECT * FROM opt_out_registry")).fetchall()
    print(f"PostgreSQL opt_out_registry rows: {len(oor_rows)}")
    for r in oor_rows:
        print(" ", dict(r._mapping))

print("\n=== 2. SQLITE .wapsi_data/webhook_inbox.db ===")
db_path = Path("C:/Users/arpit/Desktop/Razorpay/Razorpay/.wapsi_data/webhook_inbox.db")
if db_path.exists():
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    tables = [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    print("Tables:", tables)
    for t in tables:
        rows = cur.execute(f"SELECT * FROM {t}").fetchall()
        print(f"Table {t} ({len(rows)} rows):")
        for r in rows:
            d = dict(r)
            print("  Row:", {k: d[k] for k in d if k != 'payload_sanitized'})
            if "payload_sanitized" in d:
                print("    payload:", d["payload_sanitized"][:250])

print("\n=== 3. SQLITE .wapsi_data/opt_outs.db ===")
opt_db_path = Path("C:/Users/arpit/Desktop/Razorpay/Razorpay/.wapsi_data/opt_outs.db")
if opt_db_path.exists():
    conn = sqlite3.connect(opt_db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    tables = [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    print("Tables:", tables)
    for t in tables:
        rows = cur.execute(f"SELECT * FROM {t}").fetchall()
        print(f"Table {t} ({len(rows)} rows):")
        for r in rows:
            print("  Row:", dict(r))

print("\n=== 4. SQLITE .wapsi_data/recovery_timeline.db ===")
time_db_path = Path("C:/Users/arpit/Desktop/Razorpay/Razorpay/.wapsi_data/recovery_timeline.db")
if time_db_path.exists():
    conn = sqlite3.connect(time_db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    tables = [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    print("Tables:", tables)
    for t in tables:
        rows = cur.execute(f"SELECT * FROM {t} WHERE provider_event_id LIKE ? OR description LIKE ? OR metadata LIKE ?", (f"%{TARGET_WAMID}%", "%Hii%", f"%{TARGET_WAMID}%")).fetchall()
        print(f"Table {t} matching events ({len(rows)} rows):")
        for r in rows:
            print("  Row:", dict(r))
