"""Hardened migration runner (Phase G; design: docs/migration-runner-safety.md).

    python -m app.migrate --status                         read-only: versions, checksums, pending, lock holder
    python -m app.migrate --plan  --backup backups/db-<ts> read-only: every check, no change
    python -m app.migrate --apply --backup backups/db-<ts> apply pending migrations to BOTH stores in lockstep
    python -m app.migrate --repair --backup …              bring a lagging store up to the other (never newer)
    python -m app.migrate --adopt                          record checksums for rows applied before checksums existed,
                                                           only if each file is byte-identical to its committed version

Guarantees
- Checksums (SHA-256 of the file's exact bytes) are stored with each applied version, in the same transaction as the
  migration; any edited, missing or unadopted applied migration makes the runner refuse.
- Linting refuses transaction control, statements that cannot run in a transaction, and destructive statements
  (DROP TABLE/COLUMN/SCHEMA, TRUNCATE, DELETE FROM) in forward migrations.
- A session advisory lock per store database (always Store A, then Store B) prevents concurrent runs; a crashed
  runner's lock is released by PostgreSQL. On timeout the holder is named; it is never terminated.
- Precheck (non-`*_test` databases): `scripts/dbsafety.py precheck` must pass and the backup passed with --backup must
  verify, be < --max-backup-age hours old and cover both stores. There is no override flag.
- Lockstep: version V is applied to Store A then Store B before V+1, so a failure leaves the stores at most one
  version apart; the next normal run refuses until `--repair` (or a guarded down script) reconciles them.
- Each migration runs with `SET LOCAL lock_timeout` / `statement_timeout`, so it fails cleanly instead of queueing
  customer requests behind it.
- Structured log lines per store/version and a run log in .run/migrations/<timestamp>.json (no connection strings).

`migrate_database(url)` is the helper used by the backend test fixtures; it refuses any database whose name does not end
in `_test`.
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import hashlib
import importlib.util
import json
import logging
import re
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

import psycopg

MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "migrations"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
RUN_LOG_DIR = PROJECT_ROOT / ".run" / "migrations"
LOCK_KEY = 0x6176_635F_6D69_6772          # "avc_migr" — fixed key shared by every runner
APP_NAME = "avc-migrate"
STORE_ORDER = ("store-a", "store-b")

log = logging.getLogger("migrate")


class MigrationError(Exception):
    """A check failed; nothing (more) was changed."""


# ---- files: checksums and lint ------------------------------------------------------------------------------------
def file_checksum(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


_DOLLAR = re.compile(r"\$([A-Za-z_]*)\$.*?\$\1\$", re.S)
_COMMENT = re.compile(r"--[^\n]*")
_LITERAL = re.compile(r"'(?:[^']|'')*'")
_RULES = [
    ("transaction control", re.compile(r"^\s*(BEGIN|COMMIT|ROLLBACK|SAVEPOINT|RELEASE|START\s+TRANSACTION|END)\b", re.I | re.M)),
    ("cannot run in a transaction", re.compile(r"\bCONCURRENTLY\b|\bVACUUM\b|\bALTER\s+SYSTEM\b|\b(CREATE|DROP)\s+DATABASE\b", re.I)),
    ("destructive statement", re.compile(r"\bDROP\s+(TABLE|COLUMN|SCHEMA)\b|\bTRUNCATE\b|\bDELETE\s+FROM\b", re.I)),
]


def lint_migration(sql: str) -> list[str]:
    """Problems that make a forward migration unsafe to run (empty = fine). Dollar-quoted bodies, comments and string
    literals are ignored, so `DO $$ BEGIN … END $$` blocks and text mentioning these words are allowed."""
    body = _LITERAL.sub("''", _COMMENT.sub("", _DOLLAR.sub("$$", sql)))
    return [name for name, rx in _RULES if rx.search(body)]


def load_files(directory: Path = MIGRATIONS_DIR) -> dict[str, tuple[Path, str]]:
    """version → (path, checksum) for the top-level *.sql files (down/ scripts are never read)."""
    files: dict[str, tuple[Path, str]] = {}
    problems = []
    for path in sorted(directory.glob("*.sql")):
        issues = lint_migration(path.read_text())
        if issues:
            problems.append(f"{path.name}: {', '.join(issues)}")
        files[path.stem] = (path, file_checksum(path))
    if problems:
        raise MigrationError("migration lint failed: " + "; ".join(problems))
    return files


# ---- database state -----------------------------------------------------------------------------------------------
def db_name(url: str) -> str:
    return urlparse(url).path.lstrip("/")


def connect(url: str) -> psycopg.Connection:
    return psycopg.connect(url, autocommit=True, application_name=APP_NAME, connect_timeout=10)


def _columns(conn) -> set[str]:
    return {r[0] for r in conn.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_schema = current_schema() AND table_name = 'schema_migrations'").fetchall()}


def read_applied(conn) -> dict[str, dict]:
    """version → {checksum, applied_at, applied_by} (missing columns read as None). Read-only."""
    cols = _columns(conn)
    if not cols:
        return {}
    extra = [c if c in cols else f"NULL AS {c}" for c in ("checksum", "applied_by")]
    rows = conn.execute(f"SELECT version, applied_at, {', '.join(extra)} FROM schema_migrations ORDER BY version").fetchall()
    return {r[0]: {"applied_at": r[1], "checksum": r[2], "applied_by": r[3]} for r in rows}


def _is_empty(conn) -> bool:
    return conn.execute("SELECT count(*) FROM information_schema.tables WHERE table_schema = current_schema()").fetchone()[0] == 0


def ensure_bookkeeping(conn) -> None:
    """Create/extend schema_migrations (the one write the runner makes outside a migration). Idempotent, additive."""
    conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())")
    conn.execute("ALTER TABLE schema_migrations ADD COLUMN IF NOT EXISTS checksum TEXT, "
                 "ADD COLUMN IF NOT EXISTS applied_by TEXT, ADD COLUMN IF NOT EXISTS duration_ms INTEGER")


# ---- planning (pure) ----------------------------------------------------------------------------------------------
@dataclasses.dataclass
class Plan:
    pending: dict[str, list[str]]          # store → versions to apply, in order
    problems: list[str]

    @property
    def ok(self) -> bool:
        return not self.problems


def make_plan(applied: dict[str, dict[str, str | None]], files: dict[str, str], *, repair: bool = False) -> Plan:
    """applied: store → {version: checksum or None}; files: version → checksum."""
    problems: list[str] = []
    for store, versions in applied.items():
        for v, checksum in versions.items():
            if v not in files:
                problems.append(f"{store}: applied migration {v} is missing from this checkout")
            elif checksum is None:
                problems.append(f"{store}: {v} has no recorded checksum (run --adopt once)")
            elif checksum != files[v]:
                problems.append(f"{store}: {v} was modified after it was applied (recorded {checksum[:12]}…, file {files[v][:12]}…); "
                                f"see `git log -- backend/migrations/{v}.sql`")
    sets = {store: set(v) for store, v in applied.items()}
    union = set().union(*sets.values()) if sets else set()
    divergent = len({frozenset(s) for s in sets.values()}) > 1
    if repair:
        if not divergent:
            problems.append("--repair: the stores are already at the same version; nothing to repair")
        pending = {store: sorted(union - s) for store, s in sets.items()}
    else:
        if divergent:
            problems.append(f"stores are at different versions {({k: sorted(v) for k, v in sets.items()})}: run --repair first")
        pending = {store: sorted(set(files) - s) for store, s in sets.items()}
        # Applied versions must stay a prefix: never apply an older file after a newer one.
        for store, s in sets.items():
            older = [v for v in pending[store] if s and v < max(s)]
            if older:
                problems.append(f"{store}: {older} would be applied after the newer {max(s)} (out-of-order migration file)")
    return Plan(pending=pending, problems=problems)


# ---- locking ------------------------------------------------------------------------------------------------------
def lock_holder(conn) -> str:
    rows = conn.execute(
        "SELECT a.pid, a.application_name, a.backend_start, a.client_addr FROM pg_locks l JOIN pg_stat_activity a USING (pid) "
        "WHERE l.locktype = 'advisory' AND l.granted AND ((l.classid::bigint << 32) | l.objid::bigint) = %s", [LOCK_KEY]).fetchall()
    since = lambda t: f"since {t:%Y-%m-%d %H:%M:%S}" if t else "start time not visible"  # noqa: E731
    return "; ".join(f"pid {r[0]} ({r[1] or 'unknown app'}, {since(r[2])}, {r[3] or 'local'})" for r in rows) or "unknown"


def acquire_lock(conn, store: str, timeout_s: float, poll_s: float = 0.5) -> None:
    deadline = time.monotonic() + timeout_s
    while True:
        if conn.execute("SELECT pg_try_advisory_lock(%s)", [LOCK_KEY]).fetchone()[0]:
            return
        if time.monotonic() >= deadline:
            raise MigrationError(f"{store}: another migration run holds the lock: {lock_holder(conn)} (never terminated automatically)")
        time.sleep(poll_s)


def release_lock(conn) -> None:
    try:
        conn.execute("SELECT pg_advisory_unlock(%s)", [LOCK_KEY])
    except psycopg.Error:
        pass


# ---- applying -----------------------------------------------------------------------------------------------------
def apply_one(conn, version: str, path: Path, checksum: str, *, lock_timeout: str = "5s", statement_timeout: str = "5min") -> int:
    started = time.monotonic()
    with conn.transaction():
        conn.execute(f"SET LOCAL lock_timeout = '{lock_timeout}'")
        conn.execute(f"SET LOCAL statement_timeout = '{statement_timeout}'")
        conn.execute(path.read_text())
        ms = int((time.monotonic() - started) * 1000)
        conn.execute("INSERT INTO schema_migrations (version, checksum, applied_by, duration_ms) VALUES (%s, %s, %s, %s)",
                     [version, checksum, f"{APP_NAME}@{socket.gethostname()}", ms])
    return ms


def _load_dbsafety():
    spec = importlib.util.spec_from_file_location("dbsafety", PROJECT_ROOT / "scripts" / "dbsafety.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)   # type: ignore[union-attr]
    return mod


def default_precheck(backup: Path | None, max_backup_age_h: float) -> list[str]:
    """Container health, versions, latest backup (scripts/dbsafety.py), plus the backup the operator named."""
    if backup is None:
        return ["--backup backups/db-<timestamp> is required (create one with scripts/backup_db.sh)"]
    ds = _load_dbsafety()
    pg = ds.Pg()
    problems = list(ds.precheck(pg, max_age_hours=max_backup_age_h))
    try:
        manifest = ds.verify(pg, backup)
        age_h = (dt.datetime.now().astimezone() - dt.datetime.fromisoformat(manifest["created"])).total_seconds() / 3600
        if age_h > max_backup_age_h:
            problems.append(f"backup {backup.name} is {age_h:.1f} h old (max {max_backup_age_h} h)")
        if set(manifest["databases"]) != set(ds.STORE_DBS):
            problems.append(f"backup {backup.name} does not cover both stores")
    except ds.SafetyError as e:
        problems.append(f"backup {backup} failed verification: {e}")
    return problems


def run(urls: dict[str, str], *, apply: bool, repair: bool = False, backup: Path | None = None, lock_timeout_s: float = 30,
        max_backup_age_h: float = 24, directory: Path = MIGRATIONS_DIR, precheck: Callable[..., list[str]] = default_precheck,
        write_log: bool = True, migration_lock_timeout: str = "5s") -> dict:
    """Plan (and, with apply/repair, run) migrations for both stores. Raises MigrationError on any refused check."""
    files = load_files(directory)
    checks = {v: c for v, (_, c) in files.items()}
    test_only = all(db_name(u).endswith("_test") for u in urls.values())
    conns: dict[str, psycopg.Connection] = {}
    report = {"started": dt.datetime.now().astimezone().isoformat(), "mode": "repair" if repair else ("apply" if apply else "plan"),
              "backup": str(backup) if backup else None, "databases": {s: db_name(urls[s]) for s in STORE_ORDER}, "results": []}
    try:
        for store in STORE_ORDER:                       # always the same order → no lock-order deadlock between runners
            conns[store] = connect(urls[store])
            acquire_lock(conns[store], store, lock_timeout_s)
        # A brand-new installation (every store database has no tables at all) has nothing to back up; anything else
        # that is not a *_test database must pass the precheck.
        fresh = all(_is_empty(c) for c in conns.values())
        report["fresh_install"] = fresh
        if not test_only and not fresh:
            problems = precheck(backup, max_backup_age_h)
            if problems:
                raise MigrationError("precheck failed: " + "; ".join(problems))
        applied = {s: {v: r["checksum"] for v, r in read_applied(c).items()} for s, c in conns.items()}
        plan = make_plan(applied, checks, repair=repair)
        report["pending"] = plan.pending
        if not plan.ok:
            raise MigrationError("; ".join(plan.problems))
        if apply or repair:
            for version in sorted({v for vs in plan.pending.values() for v in vs}):   # lockstep: V on A, V on B, then V+1
                for store in STORE_ORDER:
                    if version not in plan.pending[store]:
                        continue
                    ensure_bookkeeping(conns[store])
                    path, checksum = files[version]
                    log.info("migration start store=%s version=%s", store, version)
                    try:
                        ms = apply_one(conns[store], version, path, checksum, lock_timeout=migration_lock_timeout)
                    except psycopg.Error as e:
                        msg = (str(e).splitlines() or [""])[0]
                        report["results"].append({"store": store, "version": version, "status": "failed",
                                                  "error": type(e).__name__, "sqlstate": e.sqlstate, "message": msg})
                        log.error("migration failed store=%s version=%s error=%s sqlstate=%s", store, version, type(e).__name__, e.sqlstate)
                        raise MigrationError(f"{store}: {version} failed ({type(e).__name__} {e.sqlstate}: {msg}); it was rolled back. "
                                             "The stores may now be one version apart: fix the cause, then run --repair.") from e
                    report["results"].append({"store": store, "version": version, "status": "ok", "ms": ms})
                    log.info("migration ok store=%s version=%s ms=%d", store, version, ms)
        return report
    finally:
        for c in conns.values():
            release_lock(c)
            c.close()
        report["finished"] = dt.datetime.now().astimezone().isoformat()
        if write_log and (apply or repair) and not test_only:
            RUN_LOG_DIR.mkdir(parents=True, exist_ok=True)
            (RUN_LOG_DIR / f"{time.strftime('%Y%m%d-%H%M%S')}.json").write_text(json.dumps(report, indent=2, default=str))


def adopt(urls: dict[str, str], directory: Path = MIGRATIONS_DIR, git_show: Callable[[str], bytes] | None = None) -> dict[str, list[str]]:
    """Record checksums for versions applied before checksums existed — only if the file on disk is byte-identical to
    its committed version (`git show HEAD:backend/migrations/<file>`). Any difference refuses everything."""
    def _git(rel: str) -> bytes:
        return subprocess.run(["git", "show", f"HEAD:{rel}"], cwd=PROJECT_ROOT, capture_output=True, check=True).stdout
    git_show = git_show or _git
    files = load_files(directory)
    adopted: dict[str, list[str]] = {}
    conns = {s: connect(u) for s, u in urls.items()}
    try:
        todo = {s: [v for v, r in read_applied(c).items() if r["checksum"] is None] for s, c in conns.items()}
        for versions in todo.values():
            for v in versions:
                if v not in files:
                    raise MigrationError(f"{v} is applied but missing from this checkout")
                path = files[v][0]
                try:
                    committed = git_show(f"backend/migrations/{path.name}")
                except subprocess.CalledProcessError:
                    raise MigrationError(f"{path.name} is not committed; refusing to adopt") from None
                if committed != path.read_bytes():
                    raise MigrationError(f"{path.name} differs from its committed version; investigate before adopting")
        for s, c in conns.items():
            acquire_lock(c, s, 30)
            try:
                ensure_bookkeeping(c)
                with c.transaction():
                    for v in todo[s]:
                        c.execute("UPDATE schema_migrations SET checksum = %s WHERE version = %s AND checksum IS NULL", [files[v][1], v])
                adopted[s] = todo[s]
            finally:
                release_lock(c)
    finally:
        for c in conns.values():
            c.close()
    return adopted


def status(urls: dict[str, str], directory: Path = MIGRATIONS_DIR) -> dict:
    """Read-only report: applied (with checksum state), pending, problems, current lock holder."""
    try:
        files = load_files(directory)
        lint = None
    except MigrationError as e:
        files, lint = {p.stem: (p, file_checksum(p)) for p in sorted(directory.glob("*.sql"))}, str(e)
    out: dict = {"lint": lint, "stores": {}}
    applied = {}
    for store in STORE_ORDER:
        with connect(urls[store]) as conn:
            rows = read_applied(conn)
            applied[store] = {v: r["checksum"] for v, r in rows.items()}
            holder = conn.execute(
                "SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' AND granted AND ((classid::bigint << 32) | objid::bigint) = %s",
                [LOCK_KEY]).fetchone()[0]
            out["stores"][store] = {
                "database": db_name(urls[store]),
                "applied": {v: {"checksum": (r["checksum"] or "")[:12] or None, "matches_file": r["checksum"] == files.get(v, (None, None))[1],
                                "applied_at": str(r["applied_at"]), "applied_by": r["applied_by"]} for v, r in rows.items()},
                "lock_holder": lock_holder(conn) if holder else None,
            }
    plan = make_plan(applied, {v: c for v, (_, c) in files.items()})
    for store in STORE_ORDER:
        out["stores"][store]["pending"] = plan.pending[store]
    out["problems"] = plan.problems
    return out


def pending_versions(url: str, directory: Path = MIGRATIONS_DIR) -> list[str]:
    """Migrations on disk that this database has not applied (read-only; used by the API's start-up check)."""
    with connect(url) as conn:
        done = set(read_applied(conn))
    return sorted(p.stem for p in directory.glob("*.sql") if p.stem not in done)


# ---- test databases -----------------------------------------------------------------------------------------------
def migrate_database(url: str) -> list[str]:
    """Bring ONE `*_test` database up to date (used by backend/tests/conftest.py). Refuses any other database.
    Test databases are disposable, so versions applied before checksums existed are adopted from the current files."""
    if not db_name(url).endswith("_test"):
        raise MigrationError(f"migrate_database() is for *_test databases only, not {db_name(url)!r}; use python -m app.migrate")
    files = load_files()
    applied_now = []
    with connect(url) as conn:
        acquire_lock(conn, db_name(url), 60)
        try:
            ensure_bookkeeping(conn)
            for v, r in read_applied(conn).items():
                if r["checksum"] is None and v in files:
                    conn.execute("UPDATE schema_migrations SET checksum = %s WHERE version = %s", [files[v][1], v])
            applied = {v: r["checksum"] for v, r in read_applied(conn).items()}
            plan = make_plan({"test": applied}, {v: c for v, (_, c) in files.items()})
            if not plan.ok:
                raise MigrationError("; ".join(plan.problems))
            for v in plan.pending["test"]:
                apply_one(conn, v, *files[v])
                applied_now.append(v)
        finally:
            release_lock(conn)
    return applied_now


def main(argv: list[str] | None = None) -> int:
    from .config import load_settings
    from .logging_config import configure_logging

    ap = argparse.ArgumentParser(prog="python -m app.migrate", description="Hardened two-store migration runner.")
    mode = ap.add_mutually_exclusive_group(required=True)
    for flag in ("--status", "--plan", "--apply", "--repair", "--adopt"):
        mode.add_argument(flag, action="store_true")
    ap.add_argument("--backup", type=Path)
    ap.add_argument("--lock-timeout", type=float, default=30)
    ap.add_argument("--max-backup-age", type=float, default=24, help="hours")
    args = ap.parse_args(argv)
    configure_logging()
    urls = load_settings().store_database_urls
    try:
        if args.status:
            print(json.dumps(status(urls), indent=2, default=str))
        elif args.adopt:
            print(json.dumps(adopt(urls), indent=2))
        else:
            report = run(urls, apply=args.apply, repair=args.repair, backup=args.backup, lock_timeout_s=args.lock_timeout,
                         max_backup_age_h=args.max_backup_age)
            print(json.dumps({k: report.get(k) for k in ("mode", "pending", "results")}, indent=2, default=str))
    except MigrationError as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
