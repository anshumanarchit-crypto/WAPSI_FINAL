#!/usr/bin/env python3
"""
WAPSI — Phase 3.1E: Runtime Database Rollback Utility
Safely restores DATABASE_URL in .env from 'wapsi_app' back to the administrative role
using the preserved 'WAPSI_ADMIN_DATABASE_URL' variable.

Guarantees:
1. Validates that WAPSI_ADMIN_DATABASE_URL exists in .env.
2. Verifies the administrative connection is functional before making any changes.
3. Atomically updates .env, restoring DATABASE_URL = WAPSI_ADMIN_DATABASE_URL.
4. Preserves all other environment variables and comments.
5. Never prints, logs, or exposes plaintext connection credentials.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Dict, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import psycopg2


def mask_url(url: str) -> str:
    """Masks credentials in connection string."""
    if not url:
        return "<EMPTY>"
    return re.sub(r"://([^:]+):([^@]+)@", r"://\1:***@", url)


def read_env_file(env_path: Path) -> Dict[str, str]:
    """Reads .env into dictionary."""
    env_vars: Dict[str, str] = {}
    if not env_path.exists():
        return env_vars
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            k, v = line.split("=", 1)
            env_vars[k.strip()] = v.strip().strip("'\"")
    return env_vars


def verify_admin_connection(admin_url: str) -> None:
    """Verifies administrative connection is reachable."""
    raw = admin_url.replace("postgresql+psycopg2://", "postgresql://", 1)
    if "sqlite" in raw:
        return
    try:
        conn = psycopg2.connect(raw)
        with conn.cursor() as cur:
            cur.execute("SELECT 1;")
            assert cur.fetchone()[0] == 1
        conn.close()
        print("       [PASS] Administrative connection verified reachable.")
    except Exception as e:
        print(f"       [FAIL] Administrative connection failed verification: {e}")
        raise RuntimeError("Rollback aborted: WAPSI_ADMIN_DATABASE_URL cannot establish connection.")


def rollback_runtime(env_path: Optional[Path] = None, dry_run: bool = False, skip_conn_check: bool = False) -> None:
    target_env = env_path or (REPO_ROOT / ".env")
    if not target_env.exists():
        print(f"[FAIL] Target environment file {target_env} does not exist.")
        sys.exit(1)

    env_vars = read_env_file(target_env)
    admin_url = env_vars.get("WAPSI_ADMIN_DATABASE_URL")
    if not admin_url:
        print("[FAIL] WAPSI_ADMIN_DATABASE_URL not found in .env. No administrative connection to roll back to.")
        sys.exit(1)

    current_db_url = env_vars.get("DATABASE_URL", "")

    print("=" * 75)
    print("WAPSI DATABASE RUNTIME ROLLBACK UTILITY")
    print("=" * 75)
    print(f"[*] Target Env File: {target_env}")
    print(f"[*] Current DATABASE_URL: {mask_url(current_db_url)}")
    print(f"[*] Restoring to: {mask_url(admin_url)}")

    if not skip_conn_check:
        print("[*] Verifying administrative connection before rollback...")
        verify_admin_connection(admin_url)

    if dry_run:
        print("\n[INFO] DRY-RUN MODE: Rollback preflight passed. No modifications were written to .env.")
        return

    # Atomic write to .env
    lines = target_env.read_text(encoding="utf-8").splitlines()
    new_lines = []
    database_url_restored = False

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("DATABASE_URL="):
            new_lines.append(f"DATABASE_URL={admin_url}")
            database_url_restored = True
        else:
            new_lines.append(line)

    if not database_url_restored:
        new_lines.append(f"DATABASE_URL={admin_url}")

    result_content = "\n".join(new_lines) + "\n"

    temp_fd, temp_path = tempfile.mkstemp(dir=target_env.parent, prefix=".env.tmp_")
    with os.fdopen(temp_fd, "w", encoding="utf-8") as f:
        f.write(result_content)
    os.replace(temp_path, target_env)

    print("\n[PASS] .env rollback completed successfully.")
    print("       + DATABASE_URL restored to administrative connection.")
    print("=" * 75)
    print("[SUCCESS] Rollback complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Rollback WAPSI runtime database connection to admin role.")
    parser.add_argument("--dry-run", action="store_true", help="Perform preflight without modifying .env.")
    parser.add_argument("--env-path", type=Path, default=None, help="Custom .env file path for testing.")
    args = parser.parse_args()
    rollback_runtime(env_path=args.env_path, dry_run=args.dry_run)

