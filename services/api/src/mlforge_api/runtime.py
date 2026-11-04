"""Process-wide runtime objects (settings, sandbox, worker, mastery policy)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import yaml
from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from mlforge_runner import DockerSandbox, SandboxLimits

from .backup import backup_sqlite
from .config import Settings
from .content.schema import DiagnosticSpec, MasteryPolicy
from .db import get_engine

log = logging.getLogger("mlforge.runtime")
API_DIR = Path(__file__).resolve().parents[2]


@dataclass
class Runtime:
    settings: Settings
    sandbox: DockerSandbox
    policy: MasteryPolicy
    diagnostic: DiagnosticSpec | None
    worker: object | None = None


_runtime: Runtime | None = None


def get_runtime() -> Runtime:
    if _runtime is None:
        raise RuntimeError("runtime not initialised")
    return _runtime


def set_runtime(rt: Runtime) -> None:
    global _runtime
    _runtime = rt


def build_sandbox(settings: Settings) -> DockerSandbox:
    limits = SandboxLimits(total_budget_s=settings.sandbox_timeout_s, memory_mb=settings.sandbox_memory_mb)
    return DockerSandbox(image=settings.runner_image, limits=limits)


def load_policy_and_diagnostic(content_dir: Path) -> tuple[MasteryPolicy, DiagnosticSpec | None]:
    """Static config read from content (the DB holds the versioned content itself)."""
    policy = MasteryPolicy()
    diagnostic = None
    index = content_dir / "skills.yaml"
    if index.exists():
        data = yaml.safe_load(index.read_text(encoding="utf-8")) or {}
        policy = MasteryPolicy.model_validate(data.get("mastery_policy") or {})
    diag = content_dir / "diagnostic.yaml"
    if diag.exists():
        diagnostic = DiagnosticSpec.model_validate(yaml.safe_load(diag.read_text(encoding="utf-8")))
    return policy, diagnostic


def alembic_config(url: str) -> Config:
    cfg = Config(str(API_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_DIR / "src" / "mlforge_api" / "migrations"))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def migrate(settings: Settings) -> None:
    """Upgrade to head; snapshot the SQLite file first if migrations are pending."""
    url = settings.resolved_database_url
    cfg = alembic_config(url)
    head = ScriptDirectory.from_config(cfg).get_current_head()
    with get_engine().connect() as conn:
        current = MigrationContext.configure(conn).get_current_revision()
    if current == head:
        return
    if current is not None and url.startswith("sqlite:///"):
        backup_sqlite(url, settings.data_dir / "backups", label=f"pre-migration-{current}")
    log.info("applying migrations", extra={"from": current, "to": head})
    with get_engine().begin() as conn:
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "head")
