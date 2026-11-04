"""Command line entry points: ``python -m mlforge_api.cli <command>``."""

from __future__ import annotations

import argparse
import json
import sys

from .config import get_settings


def _init():
    from .db import init_engine
    from .runtime import migrate

    settings = get_settings()
    init_engine(settings.resolved_database_url)
    migrate(settings)
    return settings


def cmd_migrate(_args) -> int:
    _init()
    print("database at head")
    return 0


def cmd_seed(args) -> int:
    from .content.loader import ContentError, load_curriculum
    from .content.seed import seed_content
    from .db import session_scope
    from .runtime import build_sandbox

    settings = _init()
    try:
        cur = load_curriculum(settings.content_dir)
    except ContentError as exc:
        print("content validation FAILED:", file=sys.stderr)
        for e in exc.errors:
            print("  -", e, file=sys.stderr)
        return 1
    print(
        f"static check ok: {len(cur.index.skills)} skills, {len(cur.lessons)} lessons, {len(cur.exercises)} exercises"
    )
    sandbox = build_sandbox(settings)
    with session_scope() as db:
        try:
            rep = seed_content(db, cur, sandbox, revalidate=args.revalidate)
        except ContentError as exc:
            for e in exc.errors:
                print("  -", e, file=sys.stderr)
            return 1
    print(f"lessons new: {rep.lessons_new}, exercises new: {rep.exercises_new}")
    print(
        f"validated now: {len(rep.validated)}; failed: {len(rep.failed)}; pending (runner unavailable): "
        f"{len(rep.pending)}"
    )
    for ex_id, r in rep.failed.items():
        print(f"  FAILED {ex_id}:")
        for c in r["checks"]:
            if not c["ok"]:
                print(f"     {c['name']}: {c['passed']}/{c['total']} {c.get('failures')}")
    for lid, r in rep.lesson_failures.items():
        print(f"  LESSON FAILED {lid}:")
        for c in r["checks"]:
            if not c["ok"]:
                print(f"     {c['name']}: {c.get('failures')}")
    if rep.pending:
        print(f"runner unavailable ({rep.runner_reason}); exercises stay inactive until `make seed` runs with Docker")
    return 0 if rep.ok else 2


def cmd_backup(_args) -> int:
    from .backup import backup_sqlite

    settings = _init()
    path = backup_sqlite(settings.resolved_database_url, settings.data_dir / "backups")
    print(path)
    return 0


def cmd_restore(args) -> int:
    from pathlib import Path

    from .backup import backup_sqlite, inspect_backup, restore_sqlite

    settings = get_settings()
    path = Path(args.file)
    report = inspect_backup(path)
    print(json.dumps(report, indent=2))
    if not report["ok"]:
        print("backup failed the schema check; nothing restored", file=sys.stderr)
        return 1
    if not args.yes:
        answer = input("This overwrites the current database. Type RESTORE to continue: ")
        if answer.strip() != "RESTORE":
            print("aborted")
            return 1
    safety = backup_sqlite(settings.resolved_database_url, settings.data_dir / "backups", label="pre-restore")
    restore_sqlite(settings.resolved_database_url, path)
    print(f"restored from {path}; previous data saved to {safety}")
    return 0


def cmd_runner_check(_args) -> int:
    from .runtime import build_sandbox

    h = build_sandbox(get_settings()).health(max_age_s=0)
    print(json.dumps(h.__dict__, indent=2))
    return 0 if h.available else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mlforge")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("migrate").set_defaults(fn=cmd_migrate)
    p = sub.add_parser("seed")
    p.add_argument("--revalidate", action="store_true", help="re-run sandbox validation for all content")
    p.set_defaults(fn=cmd_seed)
    sub.add_parser("backup").set_defaults(fn=cmd_backup)
    p = sub.add_parser("restore")
    p.add_argument("file")
    p.add_argument("--yes", action="store_true")
    p.set_defaults(fn=cmd_restore)
    sub.add_parser("runner-check").set_defaults(fn=cmd_runner_check)
    args = parser.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
