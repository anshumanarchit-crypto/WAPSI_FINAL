#!/usr/bin/env python3
"""
WAPSI Phase 1C: Direct PostgreSQL Authentication Diagnostic Script
Evaluates direct database endpoint connectivity vs. Supavisor pooler.
Zero credential exposure: All URIs, passwords, and secrets are masked.
"""

from __future__ import annotations

import os
import re
import socket
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import psycopg2
from sqlalchemy.engine.url import make_url

# Ensure repo root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from wapsi.core.config import get_settings


def mask_url(url: str) -> str:
    """Masks credentials in a database URL."""
    if not url:
        return "<EMPTY>"
    try:
        u = make_url(url)
        return u.render_as_string(hide_password=True)
    except Exception:
        return re.sub(r"(://[^:]+:)([^@]+)(@)", r"\1***\3", url)


def load_direct_url_from_env() -> Optional[str]:
    """Reads DIRECT_DATABASE_URL from .env file or environment without echoing secrets."""
    direct_url = os.environ.get("DIRECT_DATABASE_URL")
    if direct_url:
        return direct_url.strip()

    env_path = REPO_ROOT / ".env"
    if not env_path.exists():
        return None

    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if stripped.startswith("DIRECT_DATABASE_URL="):
                val = stripped.split("=", 1)[1].strip()
                # Strip potential surrounding quotes
                if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                    val = val[1:-1]
                return val
    return None


def run_diagnostic():
    print("=" * 75)
    print("WAPSI PHASE 1C: DIRECT POSTGRESQL AUTHENTICATION DIAGNOSTIC")
    print("=" * 75)

    # 1. Load DIRECT_DATABASE_URL
    direct_url = load_direct_url_from_env()
    if not direct_url:
        print("[FAIL] DIRECT_DATABASE_URL not found in .env or environment.")
        return

    masked = mask_url(direct_url)
    print(f"[*] Loaded DIRECT_DATABASE_URL (masked): {masked}")

    # 2. Parse Hostname & Port
    try:
        parsed = make_url(direct_url)
        hostname = parsed.host
        port = parsed.port or 5432
        username = parsed.username
        database = parsed.database or "postgres"
    except Exception as e:
        print(f"[FAIL] Could not parse DIRECT_DATABASE_URL: {e}")
        return

    print(f"[*] Parsed Target: host='{hostname}', port={port}, user='{username}', db='{database}'")

    # 3. Confirm not a pooler hostname
    if not hostname:
        print("[FAIL] Hostname is empty.")
        return

    if "pooler" in hostname.lower():
        print(f"[WARN] Parsed hostname '{hostname}' appears to be a pooler endpoint, not direct endpoint.")
    else:
        print(f"[PASS] Confirmed direct endpoint hostname (non-pooler): '{hostname}'")

    # 4. Check DNS Resolution (IPv4 vs IPv6)
    print(f"[*] Resolving DNS for '{hostname}' on port {port}...")
    ipv4_addrs: List[str] = []
    ipv6_addrs: List[str] = []
    try:
        addr_info = socket.getaddrinfo(hostname, port, socket.AF_UNSPEC, socket.SOCK_STREAM)
        for family, socktype, proto, canonname, sockaddr in addr_info:
            ip = sockaddr[0]
            if family == socket.AF_INET and ip not in ipv4_addrs:
                ipv4_addrs.append(ip)
            elif family == socket.AF_INET6 and ip not in ipv6_addrs:
                ipv6_addrs.append(ip)
        
        print(f"       - IPv4 Addresses found ({len(ipv4_addrs)}): {ipv4_addrs if ipv4_addrs else 'None'}")
        print(f"       - IPv6 Addresses found ({len(ipv6_addrs)}): {ipv6_addrs if ipv6_addrs else 'None'}")
    except socket.gaierror as e:
        print(f"\n[OUTCOME C] DNS Resolution Failed: {e}")
        print("            Direct endpoint hostname could not be resolved by local DNS.")
        print("            The database password could not be independently verified.")
        return

    if not ipv4_addrs and not ipv6_addrs:
        print("\n[OUTCOME C] No IP addresses returned by DNS resolution.")
        print("            The database password could not be independently verified.")
        return

    # 5. Check TCP Reachability
    print(f"[*] Probing TCP socket reachability to '{hostname}:{port}' (timeout=5s)...")
    tcp_ok = False
    target_ip = None
    try:
        # socket.create_connection tries all resolved addresses (IPv6 then IPv4)
        s = socket.create_connection((hostname, port), timeout=5)
        peer = s.getpeername()
        target_ip = peer[0]
        s.close()
        tcp_ok = True
        print(f"[PASS] TCP connection established successfully to {target_ip}:{port}")
    except Exception as e:
        print(f"[FAIL] TCP connection failed: {e}")
        print("\n[OUTCOME C] Direct connection failed due to TCP/network unreachability.")
        print("            (Supabase direct endpoints often require IPv6 routing, which may not be supported by local ISP/network).")
        print("            The database password could not be independently verified via direct connection.")
        return

    # 6. Attempt PostgreSQL Connection with psycopg2
    print("[*] Initiating single, read-only authentication handshake with psycopg2...")
    # Normalize URI for psycopg2 if needed
    psycopg2_url = direct_url
    if psycopg2_url.startswith("postgres://"):
        psycopg2_url = psycopg2_url.replace("postgres://", "postgresql://", 1)
    if "sslmode" not in psycopg2_url:
        psycopg2_url += ("&" if "?" in psycopg2_url else "?") + "sslmode=require"

    auth_success = False
    try:
        conn = psycopg2.connect(psycopg2_url, connect_timeout=8)
        auth_success = True
        print("[PASS] Direct PostgreSQL connection authenticated successfully!")
        
        # 7. Execute only: SELECT current_database(), current_user, version();
        cur = conn.cursor()
        cur.execute("SELECT current_database(), current_user, version();")
        row = cur.fetchone()
        db_curr, user_curr, ver_full = row[0], row[1], row[2]
        ver_short = ver_full.split()[0] + " " + ver_full.split()[1]

        print("       - Current Database:", db_curr)
        print("       - Current User:", user_curr)
        print("       - Server Version:", ver_short)
        
        # 8. Close connection safely
        cur.close()
        conn.close()
        print("[*] Direct connection closed cleanly.")

        print("\n" + "=" * 75)
        print("[OUTCOME A] DIRECT POSTGRESQL AUTHENTICATION SUCCEEDED!")
        print("            The database password is confirmed valid.")
        print("            Supavisor pooler may be holding stale cached credentials.")
        print("=" * 75)

        # Single controlled Session Pooler retry
        print("\n[*] Performing ONE carefully controlled Session Pooler retry using DATABASE_URL...")
        session_url = get_settings().database_url
        if session_url:
            masked_session = mask_url(session_url)
            print(f"[*] Target Pooler: {masked_session}")
            try:
                p_conn = psycopg2.connect(session_url, connect_timeout=8)
                p_cur = p_conn.cursor()
                p_cur.execute("SELECT current_database(), current_user;")
                p_row = p_cur.fetchone()
                print(f"[PASS] Session Pooler connected! db={p_row[0]}, user={p_row[1]}")
                p_cur.close()
                p_conn.close()
                print("[*] Session Pooler verification succeeded!")
            except Exception as pool_err:
                print(f"[NOTICE] Session Pooler retry result: {pool_err}")
        return

    except psycopg2.OperationalError as e:
        err_msg = str(e)
        pgcode = getattr(e, "pgcode", None)
        print(f"[FAIL] OperationalError during connection: {err_msg.splitlines()[0]}")
        if pgcode:
            print(f"       SQLSTATE Error Code: {pgcode}")

        if "28P01" in err_msg or "password authentication failed" in err_msg or pgcode == "28P01":
            print("\n" + "=" * 75)
            print("[OUTCOME B] DIRECT CONNECTION FAILED WITH PASSWORD AUTHENTICATION (28P01)")
            print("            The credentials in DIRECT_DATABASE_URL were rejected by PostgreSQL.")
            print("=" * 75)
        else:
            print("\n" + "=" * 75)
            print(f"[OUTCOME C] Direct connection failed with non-auth operational error: {err_msg.splitlines()[0]}")
            print("=" * 75)
    except Exception as e:
        print(f"[OUTCOME C] Unexpected error: {e}")


if __name__ == "__main__":
    run_diagnostic()

