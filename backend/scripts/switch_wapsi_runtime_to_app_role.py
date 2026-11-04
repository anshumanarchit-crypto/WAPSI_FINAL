#!/usr/bin/env python3
"""
WAPSI — Phase 3.1E: Secure Runtime Database Cutover Utility
Safely cuts over DATABASE_URL in .env from the administrative role to 'wapsi_app'.

Guarantees:
1. Loads .env privately without printing secrets.
2. Confirms existing administrative connection is functional.
3. Securely prompts for 'wapsi_app' password (or reads WAPSI_APP_PASSWORD env var).
4. Verifies new connection via raw psycopg2 and SQLAlchemy (Session Pooler port 5432, SSL required).
5. Asserts current_user == 'wapsi_app', rolsuper == False, rolbypassrls == False.
6. Verifies table permissions (permitted SELECTs, 42501 on sensitive tables, 42501 on DELETE).
7. Verifies public.lookup_merchant_by_api_key_hash(text).
8. Only after all preflight tests pass, atomically updates .env:
   - Stores original admin URL in WAPSI_ADMIN_DATABASE_URL (for rollback).
   - Replaces DATABASE_URL with the wapsi_app connection string.
9. Supports --dry-run for non-mutating preflight validation.
"""

from __future__ import annotations

import argparse
import getpass
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from urllib.parse import quote_plus, urlparse

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import psycopg2
from sqlalchemy import create_engine, text


def mask_url(url: str) -> str:
    """Masks credentials in a PostgreSQL URL."""
    if not url:
        return "<EMPTY>"
    return re.sub(r"://([^:]+):([^@]+)@", r"://\1:***@", url)


def read_env_file(env_path: Path) -> Dict[str, str]:
    """Reads .env into key-value dictionary preserving raw strings."""
    env_vars: Dict[str, str] = {}
    if not env_path.exists():
        return env_vars
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            k, v = line.split("=", 1)
            k = k.strip()
            v = v.strip().strip("'\"")
            env_vars[k] = v
    return env_vars


def get_password(provided_password: Optional[str] = None) -> str:
    """Prompts for password securely without echoing."""
    if provided_password:
        return provided_password
    env_pwd = os.environ.get("WAPSI_APP_PASSWORD")
    if env_pwd:
        return env_pwd
    if sys.stdin.isatty():
        return getpass.getpass("Enter provisioned password for 'wapsi_app': ")
    sys.stderr.write("Enter provisioned password for 'wapsi_app': ")
    sys.stderr.flush()
    return sys.stdin.readline().rstrip("\r\n")


def build_app_url(admin_url: str, app_password: str, project_ref: str = "filofxijqmgluuulivxb") -> Tuple[str, str]:
    """Constructs psycopg2 and SQLAlchemy URLs for wapsi_app."""
    raw = admin_url
    if raw.startswith("postgresql+psycopg2://"):
        raw = raw.replace("postgresql+psycopg2://", "postgresql://", 1)
    parsed = urlparse(raw)
    host = parsed.hostname or "aws-0-ap-south-1.pooler.supabase.com"
    port = parsed.port or 5432
    dbname = (parsed.path or "/postgres").lstrip("/")

    username = f"wapsi_app.{project_ref}"
    encoded_pwd = quote_plus(app_password)

    pg_url = f"postgresql://{username}:{encoded_pwd}@{host}:{port}/{dbname}?sslmode=require"
    sa_url = f"postgresql+psycopg2://{username}:{encoded_pwd}@{host}:{port}/{dbname}?sslmode=require"
    return pg_url, sa_url


def run_preflight_checks(admin_url: str, app_pg_url: str, app_sa_url: str) -> None:
    """Runs all 10 preflight safety checks."""
    print("[*] 1. Checking administrative connection health...")
    raw_admin = admin_url.replace("postgresql+psycopg2://", "postgresql://", 1)
    try:
        adm_conn = psycopg2.connect(raw_admin)
        with adm_conn.cursor() as cur:
            cur.execute("SELECT current_user, rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user;")
            user, is_super, bypass_rls = cur.fetchone()
            print(f"       + Current Admin Role: {user} (rolsuper={is_super}, rolbypassrls={bypass_rls})")
        adm_conn.close()
        print("       [PASS] Administrative database connection verified.")
    except Exception as e:
        print(f"       [FAIL] Administrative connection failed: {e}")
        raise RuntimeError("Administrative connection failed preflight check.")

    print("\n[*] 2. Checking Session Pooler TLS connection as 'wapsi_app'...")
    try:
        app_conn = psycopg2.connect(app_pg_url)
        with app_conn.cursor() as cur:
            cur.execute("SELECT current_user, current_database();")
            u, d = cur.fetchone()
            assert u == "wapsi_app", f"Expected current_user 'wapsi_app', got '{u}'"
            print(f"       + Connected User: {u}, Database: {d}")

            assert app_conn.info.ssl_in_use is True, "SSL must be enabled"
            print("       + TLS Encryption: ACTIVE (sslmode=require)")

            cur.execute("SELECT rolcanlogin, rolsuper, rolbypassrls FROM pg_roles WHERE rolname = 'wapsi_app';")
            can_login, rolsuper, rolbypassrls = cur.fetchone()
            assert can_login is True
            assert rolsuper is False
            assert rolbypassrls is False
            print(f"       + Restricted Attributes: rolsuper={rolsuper}, rolbypassrls={rolbypassrls}")

        app_conn.close()
        print("       [PASS] Raw psycopg2 Session Pooler connection verified.")
    except Exception as e:
        print(f"       [FAIL] Raw connection as 'wapsi_app' failed: {e}")
        raise RuntimeError(f"Application connection failed: {e}")

    print("\n[*] 3. Checking SQLAlchemy 2.0 connection pool...")
    try:
        engine = create_engine(app_sa_url, pool_pre_ping=True, connect_args={"sslmode": "require"})
        with engine.connect() as conn:
            val = conn.execute(text("SELECT 1;")).scalar()
            assert val == 1
        print("       [PASS] SQLAlchemy connection pool pre-ping passed.")
    except Exception as e:
        print(f"       [FAIL] SQLAlchemy connection failed: {e}")
        raise RuntimeError(f"SQLAlchemy connection failed: {e}")

    print("\n[*] 4. Checking table permissions & security boundaries...")
    app_conn = psycopg2.connect(app_pg_url)
    app_conn.autocommit = False
    cur = app_conn.cursor()
    try:
        # Permitted table SELECT
        for tbl in ["merchants", "transactions", "customers", "recovery_outbox", "opt_out_registry"]:
            cur.execute(f"SELECT count(*) FROM public.{tbl};")
            assert cur.fetchone()[0] == 0
        print("       [PASS] SELECT on permitted tables verified (0 rows).")

        # Prohibited sensitive tables
        for stbl in ["merchant_api_keys", "merchant_memberships"]:
            try:
                cur.execute(f"SELECT * FROM public.{stbl} LIMIT 1;")
                raise RuntimeError(f"Expected access denied on {stbl}, but query succeeded!")
            except psycopg2.errors.InsufficientPrivilege:
                app_conn.rollback()
        print("       [PASS] Access denied (42501) on merchant_api_keys & merchant_memberships.")

        # Prohibited DELETE operations
        for dtbl in ["transactions", "customers", "recovery_outbox", "opt_out_registry"]:
            try:
                cur.execute(f"DELETE FROM public.{dtbl} WHERE 1=0;")
                raise RuntimeError(f"Expected DELETE to be denied on {dtbl}, but query succeeded!")
            except psycopg2.errors.InsufficientPrivilege:
                app_conn.rollback()
        print("       [PASS] Zero DELETE privileges verified (42501).")

        # Function Execution Check
        dummy_hash = "c" * 64
        cur.execute("SELECT * FROM public.lookup_merchant_by_api_key_hash(%s);", (dummy_hash,))
        assert len(cur.fetchall()) == 0
        print("       [PASS] public.lookup_merchant_by_api_key_hash verified executable by 'wapsi_app'.")

    finally:
        app_conn.close()


def update_env_file(env_path: Path, new_sa_url: str, current_admin_url: str) -> None:
    """Atomically updates .env with backup variable."""
    content = env_path.read_text(encoding="utf-8") if env_path.exists() else ""
    lines = content.splitlines()
    new_lines = []
    database_url_updated = False
    has_admin_url = False

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("WAPSI_ADMIN_DATABASE_URL="):
            has_admin_url = True
            new_lines.append(line)
        elif stripped.startswith("DATABASE_URL="):
            if not has_admin_url and not any(l.strip().startswith("WAPSI_ADMIN_DATABASE_URL=") for l in lines):
                new_lines.append(f"WAPSI_ADMIN_DATABASE_URL={current_admin_url}")
                has_admin_url = True
            new_lines.append(f"DATABASE_URL={new_sa_url}")
            database_url_updated = True
        else:
            new_lines.append(line)

    if not database_url_updated:
        if not has_admin_url:
            new_lines.append(f"WAPSI_ADMIN_DATABASE_URL={current_admin_url}")
        new_lines.append(f"DATABASE_URL={new_sa_url}")

    result_content = "\n".join(new_lines) + "\n"

    # Atomic write via tempfile in same directory
    temp_fd, temp_path = tempfile.mkstemp(dir=env_path.parent, prefix=".env.tmp_")
    with os.fdopen(temp_fd, "w", encoding="utf-8") as f:
        f.write(result_content)
    os.replace(temp_path, env_path)


def switch_runtime(env_path: Optional[Path] = None, password: Optional[str] = None, dry_run: bool = False) -> None:
    target_env = env_path or (REPO_ROOT / ".env")
    if not target_env.exists():
        print(f"[FAIL] Target environment file {target_env} does not exist.")
        sys.exit(1)

    env_vars = read_env_file(target_env)
    admin_url = env_vars.get("DATABASE_URL")
    if not admin_url:
        print("[FAIL] No DATABASE_URL found in target .env.")
        sys.exit(1)

    print("=" * 75)
    print("WAPSI DATABASE RUNTIME CUTOVER PREFLIGHT & SWITCH UTILITY")
    print("=" * 75)
    print(f"[*] Target Env File: {target_env}")
    print(f"[*] Current DATABASE_URL: {mask_url(admin_url)}")

    app_pwd = get_password(password)
    if not app_pwd:
        print("[FAIL] Password cannot be empty.")
        sys.exit(1)

    app_pg_url, app_sa_url = build_app_url(admin_url, app_pwd)
    print(f"[*] Target wapsi_app URL: {mask_url(app_sa_url)}")

    # Run comprehensive preflight checks
    run_preflight_checks(admin_url, app_pg_url, app_sa_url)

    if dry_run:
        print("\n[INFO] DRY-RUN MODE: Preflight passed. No modifications were written to .env.")
        return

    print("\n[*] Updating .env atomically...")
    update_env_file(target_env, app_sa_url, admin_url)
    print("[PASS] .env updated successfully.")
    print("       + DATABASE_URL set to restricted 'wapsi_app' role.")
    print("       + Original admin URL preserved in 'WAPSI_ADMIN_DATABASE_URL'.")
    print("=" * 75)
    print("[SUCCESS] Runtime database cutover complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Switch WAPSI runtime database connection to wapsi_app.")
    parser.add_argument("--dry-run", action="store_true", help="Perform preflight checks without modifying .env.")
    parser.add_argument("--env-path", type=Path, default=None, help="Custom .env file path for testing.")
    args = parser.parse_args()
    switch_runtime(env_path=args.env_path, dry_run=args.dry_run)

