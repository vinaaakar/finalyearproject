#!/usr/bin/env python3
"""Database safety tooling for the two store databases (local only; nothing is uploaded anywhere).

  backup         custom-format pg_dump of each database → backups/db-<timestamp>/ (git-ignored, owner-only),
                 SHA-256 checksums, readable-TOC check, per-table row counts (dump == live), MANIFEST.json
  verify DIR     re-check an existing backup: checksums, TOC readable, dump row counts == manifest
  restore-check DIR --confirm
                 restore each dump into a NEW scratch database <db>_restorecheck_<timestamp>, compare row counts
                 with the manifest, then drop the scratch database. The original databases are never written to,
                 and only names matching the scratch pattern can ever be created or dropped.
  precheck       read-only two-store migration readiness: container healthy, both databases reachable, both at the
                 same applied migration versions, the same pending migrations, and a verified backup that is recent.

Runs Postgres client tools inside the project container (`docker exec avc_postgres …`); never runs Docker Compose,
never starts/stops/recreates the container. Usage: backend/.venv/bin/python scripts/dbsafety.py <command> …
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]
BACKUP_ROOT = ROOT / "backups"
MIGRATIONS_DIR = ROOT / "backend" / "migrations"
CONTAINER = os.environ.get("AVC_PG_CONTAINER", "avc_postgres")
STORE_DBS = ("store_a", "store_b")
DB_NAME_RE = re.compile(r"^store_[ab](_test)?$")
SCRATCH_RE = re.compile(r"^store_[ab](_test)?_restorecheck_\d{8}_\d{6}$")
MAX_BACKUP_AGE_HOURS = 24

Runner = Callable[[list[str], bytes | None], bytes]


class SafetyError(Exception):
    pass


def docker_runner(args: list[str], stdin: bytes | None = None) -> bytes:
    """Run `docker <args>`; raises SafetyError with stderr on failure."""
    proc = subprocess.run(["docker", *args], input=stdin, capture_output=True)
    if proc.returncode != 0:
        raise SafetyError(f"docker {' '.join(args[:3])}… failed: {proc.stderr.decode(errors='replace').strip()[:300]}")
    return proc.stdout


class Pg:
    """Postgres client commands inside the container (as the postgres superuser over the local socket)."""

    def __init__(self, run: Runner = docker_runner, container: str = CONTAINER):
        self.run, self.container = run, container

    def _exec(self, cmd: list[str], stdin: bytes | None = None) -> bytes:
        return self.run(["exec", *(["-i"] if stdin is not None else []), self.container, *cmd], stdin)

    def healthy(self) -> bool:
        try:
            out = self.run(["inspect", "-f", "{{.State.Status}}:{{if .State.Health}}{{.State.Health.Status}}{{end}}", self.container], None)
        except SafetyError:
            return False
        return out.decode().strip() == "running:healthy"

    def container_id(self) -> str:
        return self.run(["inspect", "-f", "{{.Id}}", self.container], None).decode().strip()[:12]

    def psql(self, db: str, sql: str) -> str:
        return self._exec(["psql", "-U", "postgres", "-d", db, "-At", "-v", "ON_ERROR_STOP=1", "-c", sql]).decode()

    def databases(self) -> set[str]:
        return set(filter(None, self.psql("postgres", "SELECT datname FROM pg_database").split()))

    def table_counts(self, db: str) -> dict[str, int]:
        tables = [t for t in self.psql(db, "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' "
                                           "AND table_type = 'BASE TABLE' ORDER BY 1").split() if t]
        if not tables:
            return {}
        sql = " UNION ALL ".join(f"SELECT '{t}', count(*) FROM public.\"{t}\"" for t in tables)
        return {line.split("|")[0]: int(line.split("|")[1]) for line in self.psql(db, sql).splitlines() if "|" in line}

    def dump(self, db: str) -> bytes:
        return self._exec(["pg_dump", "-U", "postgres", "-Fc", db])

    def toc_entries(self, dump: bytes) -> int:
        toc = self._exec(["pg_restore", "--list"], dump).decode()
        m = re.search(r"TOC Entries:\s*(\d+)", toc)
        if not m:
            raise SafetyError("dump TOC is not readable")
        return int(m.group(1))

    def dump_counts(self, dump: bytes) -> dict[str, int]:
        sql = self._exec(["pg_restore", "-f", "-"], dump).decode(errors="replace")
        counts: dict[str, int] = {}
        table, n = None, 0
        for line in sql.splitlines():
            if table is None:
                m = re.match(r"^COPY public\.\"?([\w]+)\"? ", line)
                if m:
                    table, n = m.group(1), 0
            elif line == "\\.":
                counts[table], table = n, None
            else:
                n += 1
        return counts


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _now() -> dt.datetime:
    return dt.datetime.now().astimezone()


# ---- backup ------------------------------------------------------------------------------------------------
def backup(pg: Pg, dbs: tuple[str, ...] = STORE_DBS, root: Path | None = None, now: dt.datetime | None = None) -> Path:
    root = root or BACKUP_ROOT   # resolved at call time (never bound at import)
    for db in dbs:
        if not DB_NAME_RE.match(db):
            raise SafetyError(f"refusing unknown database name {db!r}")
    if not pg.healthy():
        raise SafetyError(f"container {CONTAINER} is not running and healthy; nothing was done (this tool never starts it)")
    now = now or _now()
    out = root / f"db-{now.strftime('%Y%m%d-%H%M%S')}"
    if out.resolve().parent != root.resolve():
        raise SafetyError("backups may only be written under backups/")
    out.mkdir(parents=True, exist_ok=False, mode=0o700)
    manifest = {"created": now.isoformat(), "container_id": pg.container_id(), "tool": "scripts/dbsafety.py", "databases": {}}
    for db in dbs:
        live_before = pg.table_counts(db)
        data = pg.dump(db)
        if not data:
            raise SafetyError(f"empty dump for {db}")
        path = out / f"{db}.dump"
        path.write_bytes(data)
        os.chmod(path, 0o600)
        in_dump = pg.dump_counts(data)
        live_after = pg.table_counts(db)
        if in_dump != live_before or live_before != live_after:
            raise SafetyError(f"{db}: row counts differ (live before/after vs dump) — data changed during the backup or the dump "
                              f"is incomplete: {sorted(set(in_dump.items()) ^ set(live_before.items()))[:6]}")
        manifest["databases"][db] = {"file": path.name, "bytes": len(data), "sha256": sha256(data),
                                     "toc_entries": pg.toc_entries(data), "tables": in_dump}
    (out / "MANIFEST.json").write_text(json.dumps(manifest, indent=2, sort_keys=True))
    os.chmod(out / "MANIFEST.json", 0o600)
    return out


def _load(backup_dir: Path) -> dict:
    backup_dir = backup_dir.resolve()
    if backup_dir.parent != BACKUP_ROOT.resolve() and BACKUP_ROOT.resolve() not in backup_dir.parents:
        raise SafetyError("backup directory must be inside backups/")
    try:
        return json.loads((backup_dir / "MANIFEST.json").read_text())
    except FileNotFoundError:
        raise SafetyError("MANIFEST.json not found in that directory") from None


def verify(pg: Pg, backup_dir: Path) -> dict:
    manifest = _load(backup_dir)
    for db, info in manifest["databases"].items():
        data = (backup_dir / info["file"]).read_bytes()
        if sha256(data) != info["sha256"]:
            raise SafetyError(f"{db}: checksum mismatch — the backup file was changed or corrupted")
        if pg.toc_entries(data) != info["toc_entries"]:
            raise SafetyError(f"{db}: TOC differs from the manifest")
        if pg.dump_counts(data) != info["tables"]:
            raise SafetyError(f"{db}: dump row counts differ from the manifest")
    return manifest


# ---- restore check (scratch databases only) ------------------------------------------------------------------
def scratch_name(db: str, now: dt.datetime) -> str:
    name = f"{db}_restorecheck_{now.strftime('%Y%m%d_%H%M%S')}"
    if not SCRATCH_RE.match(name) or name == db:
        raise SafetyError(f"unsafe scratch database name {name!r}")
    return name


def _guard_scratch(name: str, originals: set[str]) -> None:
    if not SCRATCH_RE.match(name) or name in originals or name in STORE_DBS:
        raise SafetyError(f"refusing to touch {name!r}: only *_restorecheck_<timestamp> scratch databases may be created or dropped")


def restore_check(pg: Pg, backup_dir: Path, confirm: bool, now: dt.datetime | None = None) -> dict[str, str]:
    if not confirm:
        raise SafetyError("restore-check creates and drops scratch databases on the live Postgres instance; re-run with --confirm")
    manifest = verify(pg, backup_dir)          # never restore an unverified backup
    now = now or _now()
    existing = pg.databases()
    results: dict[str, str] = {}
    for db, info in manifest["databases"].items():
        scratch = scratch_name(db, now)
        _guard_scratch(scratch, {d for d in existing if not SCRATCH_RE.match(d)})
        if scratch in existing:
            raise SafetyError(f"{scratch} already exists; refusing to reuse it")
        pg.psql("postgres", f'CREATE DATABASE "{scratch}"')
        try:
            pg._exec(["pg_restore", "-U", "postgres", "--no-owner", "--no-privileges", "--exit-on-error", "-d", scratch],
                     (backup_dir / info["file"]).read_bytes())
            restored = pg.table_counts(scratch)
            if restored != info["tables"]:
                raise SafetyError(f"{db}: restored row counts differ from the manifest")
            results[db] = f"OK — restored into {scratch}; {len(restored)} tables, row counts match"
        finally:
            _guard_scratch(scratch, {d for d in existing if not SCRATCH_RE.match(d)})
            pg.psql("postgres", f'DROP DATABASE IF EXISTS "{scratch}"')
    return results


# ---- two-store migration precheck (read-only) --------------------------------------------------------------
def available_migrations(directory: Path | None = None) -> list[str]:
    directory = directory or MIGRATIONS_DIR
    return sorted(p.stem for p in directory.glob("*.sql"))   # top level only: down/ scripts are never applied


def latest_backup(root: Path | None = None) -> Path | None:
    root = root or BACKUP_ROOT
    candidates = sorted(p for p in root.glob("db-*") if (p / "MANIFEST.json").exists()) if root.exists() else []
    return candidates[-1] if candidates else None


def precheck(pg: Pg, dbs: tuple[str, ...] = STORE_DBS, now: dt.datetime | None = None,
             max_age_hours: float = MAX_BACKUP_AGE_HOURS) -> list[str]:
    """Problems that must be fixed before migrating (empty list = ready)."""
    problems: list[str] = []
    if not pg.healthy():
        return [f"container {CONTAINER} is not running and healthy"]
    available = available_migrations()
    applied: dict[str, list[str]] = {}
    for db in dbs:
        try:
            applied[db] = sorted(filter(None, pg.psql(db, "SELECT version FROM schema_migrations ORDER BY 1").split()))
        except SafetyError as e:
            problems.append(f"{db}: not reachable or has no schema_migrations ({e})")
    if len(applied) == len(dbs):
        if len({tuple(v) for v in applied.values()}) != 1:
            problems.append(f"stores are at different migration versions: {applied} — repair the lagging store before anything new")
        for db, versions in applied.items():
            unknown = sorted(set(versions) - set(available))
            if unknown:
                problems.append(f"{db}: applied migrations missing from this checkout: {unknown}")
    latest = latest_backup()
    if latest is None:
        problems.append("no backup found: run `scripts/backup_db.sh` first")
    else:
        try:
            manifest = verify(pg, latest)
            age = ((now or _now()) - dt.datetime.fromisoformat(manifest["created"])).total_seconds() / 3600
            if age > max_age_hours:
                problems.append(f"latest backup {latest.name} is {age:.1f} h old (max {max_age_hours} h)")
            if set(manifest["databases"]) != set(dbs):
                problems.append(f"latest backup {latest.name} does not cover {sorted(set(dbs) - set(manifest['databases']))}")
        except SafetyError as e:
            problems.append(f"latest backup {latest.name} failed verification: {e}")
    return problems


def pending(pg: Pg, db: str) -> list[str]:
    applied = set(filter(None, pg.psql(db, "SELECT version FROM schema_migrations").split()))
    return [m for m in available_migrations() if m not in applied]


# ---- CLI ---------------------------------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("backup")
    v = sub.add_parser("verify"); v.add_argument("dir", type=Path)
    r = sub.add_parser("restore-check"); r.add_argument("dir", type=Path); r.add_argument("--confirm", action="store_true")
    sub.add_parser("precheck")
    args = ap.parse_args(argv)
    os.umask(0o077)
    pg = Pg()
    try:
        if args.cmd == "backup":
            out = backup(pg)
            m = json.loads((out / "MANIFEST.json").read_text())
            print(f"Backup written to {out.relative_to(ROOT)}")
            for db, info in m["databases"].items():
                print(f"  {db}: {info['bytes']} bytes, {len(info['tables'])} tables, sha256 {info['sha256'][:16]}…, row counts verified")
        elif args.cmd == "verify":
            verify(pg, args.dir)
            print(f"{args.dir}: checksums, TOC and row counts OK")
        elif args.cmd == "restore-check":
            for db, msg in restore_check(pg, args.dir, args.confirm).items():
                print(f"  {db}: {msg}")
        elif args.cmd == "precheck":
            problems = precheck(pg)
            for db in STORE_DBS:
                print(f"  {db}: pending migrations {pending(pg, db) or 'none'}")
            if problems:
                print("NOT READY:\n  - " + "\n  - ".join(problems))
                return 1
            print("Ready: both stores at the same version, backup recent and verified.")
    except SafetyError as e:
        print(f"!! {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
