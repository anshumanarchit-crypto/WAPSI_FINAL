"""
Unit and Integration Config Tests for WAPSI Phase 1C: Real PostgreSQL Integration.
Target: WAPSI-DEV-MUMBAI (filofxijqmgluuulivxb, ap-south-1)
"""

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy.engine import Engine

from wapsi.core.config import get_settings
from wapsi.db.models import Base
from wapsi.db.session import DatabaseManager
from scripts.verify_postgres_connection import (
    EXPECTED_MIGRATIONS,
    EXPECTED_TABLES,
    mask_url,
    verify_postgres,
)


def test_postgres_driver_installed():
    """Verifies that psycopg2-binary driver is installed and operational."""
    import psycopg2
    assert hasattr(psycopg2, "__version__")
    assert psycopg2.__version__ is not None


def test_orm_models_match_expected_tables():
    """Verifies that all 15 ORM models map to the 15 expected public schema tables."""
    orm_tables = set(Base.metadata.tables.keys())
    expected_set = set(EXPECTED_TABLES)

    assert orm_tables == expected_set, f"ORM tables do not match expected tables. Diff: {orm_tables ^ expected_set}"
    assert len(orm_tables) == 15


def test_mask_url_safety():
    """Verifies that sensitive credentials are never leaked in connection strings."""
    url = "postgresql://postgres.filofxijqmgluuulivxb:SecretP@ssw0rd!@aws-0-ap-south-1.pooler.supabase.com:5432/postgres"
    masked = mask_url(url)
    assert "SecretP@ssw0rd!" not in masked
    assert ":***@" in masked
    assert "aws-0-ap-south-1.pooler.supabase.com" in masked
    assert "postgres.filofxijqmgluuulivxb" in masked


def test_database_manager_postgres_pool_configuration():
    """Verifies that DatabaseManager sets production pooling for PostgreSQL URLs."""
    dummy_pg_url = "postgresql://user:pass@remote-host:5432/testdb"
    
    # We patch create_engine to inspect the arguments passed to create_engine
    with patch("wapsi.db.session.create_engine") as mock_create_engine:
        DatabaseManager(database_url=dummy_pg_url)
        mock_create_engine.assert_called_once()
        call_args, call_kwargs = mock_create_engine.call_args
        
        # Dialect conversion
        assert call_args[0] == "postgresql+psycopg2://user:pass@remote-host:5432/testdb"
        assert call_kwargs["pool_size"] == 10
        assert call_kwargs["max_overflow"] == 5
        assert call_kwargs["pool_recycle"] == 300
        assert call_kwargs["pool_pre_ping"] is True
        assert call_kwargs["connect_args"]["sslmode"] == "require"


def test_verify_script_rejects_empty_database_url():
    """Verifies that verify_postgres_connection fails when DATABASE_URL is unset."""
    with patch.dict(os.environ, {"DATABASE_URL": ""}, clear=False):
        with patch("scripts.verify_postgres_connection.get_settings") as mock_settings:
            mock_settings.return_value.database_url = None
            res = verify_postgres()
            assert res is False


def test_verify_script_rejects_sqlite_url():
    """Verifies that verify_postgres_connection strictly refuses SQLite in Phase 1C."""
    with patch.dict(os.environ, {"DATABASE_URL": "sqlite:///:memory:"}, clear=False):
        res = verify_postgres()
        assert res is False

