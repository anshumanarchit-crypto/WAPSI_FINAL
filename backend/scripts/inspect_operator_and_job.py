import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from wapsi.db.session import DatabaseManager
from sqlalchemy import text

dm = DatabaseManager()
with dm.session_scope() as session:
    m_rows = session.execute(text("SELECT id, name, merchant_code, status FROM merchants")).fetchall()
    print("Merchants:")
    for r in m_rows:
        print(" ", dict(r._mapping))

    mem_rows = session.execute(text("SELECT id, merchant_id, user_id, role, is_active FROM merchant_memberships")).fetchall()
    print("Merchant Memberships:")
    for r in mem_rows:
        print(" ", dict(r._mapping))

    k_rows = session.execute(text("SELECT id, merchant_id, key_prefix, label, is_active, scopes FROM merchant_api_keys")).fetchall()
    print("Merchant API Keys:")
    for r in k_rows:
        print(" ", dict(r._mapping))
