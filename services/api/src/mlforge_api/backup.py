"""Consistent SQLite backups/restores (uses the online backup API, WAL-safe).

Backups contain learning data only: secrets live in the environment, never
in the database, so no secret is ever written to a backup file.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

REQUIRED_TABLES = {"profiles", "skills", "submissions", "run_jobs", "skill_evidence", "alembic_version"}


def db_path_from_url(url: str) -> Path:
    if not url.startswith("sqlite:///"):
        raise ValueError("backups are only supported for SQLite")
    return Path(url.removeprefix("sqlite:///"))


def backup_sqlite(url: str, dest_dir: Path, label: str = "manual") -> Path:
    src = db_path_from_url(url)
    dest_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    dest = dest_dir / f"mlforge-{label}-{stamp}.db"
    with sqlite3.connect(src) as source, sqlite3.connect(dest) as target:
        source.backup(target)
    return dest


def inspect_backup(path: Path) -> dict:
    """Schema check before a restore: integrity + required tables + revision."""
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as conn:
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        revision = None
        if "alembic_version" in tables:
            row = conn.execute("SELECT version_num FROM alembic_version").fetchone()
            revision = row[0] if row else None
        profiles = conn.execute("SELECT count(*) FROM profiles").fetchone()[0] if "profiles" in tables else 0
    missing = sorted(REQUIRED_TABLES - tables)
    return {
        "ok": integrity == "ok" and not missing,
        "integrity": integrity,
        "missing_tables": missing,
        "revision": revision,
        "profiles": profiles,
    }


def restore_sqlite(url: str, backup: Path) -> None:
    dest = db_path_from_url(url)
    with sqlite3.connect(backup) as source, sqlite3.connect(dest) as target:
        source.backup(target)
