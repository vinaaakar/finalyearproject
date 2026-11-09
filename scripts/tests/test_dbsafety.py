"""Tests for scripts/dbsafety.py against a FAKE docker (no real database, container or file outside tmp is touched)."""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import dbsafety  # noqa: E402

NOW = dt.datetime(2026, 11, 9, 14, 0, 0, tzinfo=dt.timezone.utc)


class FakeDocker:
    def __init__(self, healthy=True):
        self.healthy = healthy
        self.calls: list[list[str]] = []
        self.dbs = {"postgres": {},
                    "store_a": {"products": 10, "orders": 6, "schema_migrations": 3},
                    "store_b": {"products": 10, "orders": 4, "schema_migrations": 3}}
        self.versions = {"store_a": ["0001_a", "0002_b"], "store_b": ["0001_a", "0002_b"]}
        self.mutate_after_dump = None   # db name whose rows change during the backup

    def __call__(self, args, stdin=None):
        self.calls.append(args)
        if args[0] == "inspect":
            if "{{.Id}}" in args:
                return b"4c79018cc9ef1234567890\n"
            return b"running:healthy\n" if self.healthy else b"exited:\n"
        assert args[0] == "exec", args
        cmd = [a for a in args[1:] if a != "-i"][1:]       # drop container name
        tool = cmd[0]
        if tool == "pg_dump":
            db = cmd[-1]
            if self.mutate_after_dump == db:
                self.dbs[db]["orders"] += 1
            return json.dumps({"db": db, "tables": self.dbs[db]}).encode()
        if tool == "pg_restore" and "--list" in cmd:
            return b";\n; Archive created\n;     TOC Entries: 42\n"
        if tool == "pg_restore" and "-f" in cmd:
            tables = json.loads(stdin)["tables"]
            out = []
            for t, n in tables.items():
                out.append(f"COPY public.{t} (id) FROM stdin;")
                out += [str(i) for i in range(n)]
                out.append("\\.")
            return "\n".join(out).encode()
        if tool == "pg_restore" and "-d" in cmd:
            target = cmd[cmd.index("-d") + 1]
            self.dbs[target] = dict(json.loads(stdin)["tables"])
            return b""
        if tool == "psql":
            db, sql = cmd[cmd.index("-d") + 1], cmd[cmd.index("-c") + 1]
            if sql.startswith("CREATE DATABASE"):
                self.dbs[sql.split('"')[1]] = {}
                return b""
            if sql.startswith("DROP DATABASE"):
                self.dbs.pop(sql.split('"')[1], None)
                return b""
            if "FROM pg_database" in sql:
                return "\n".join(self.dbs).encode()
            if "information_schema.tables" in sql:
                return "\n".join(sorted(self.dbs[db])).encode()
            if "UNION ALL" in sql or "count(*)" in sql:
                return "\n".join(f"{t}|{n}" for t, n in sorted(self.dbs[db].items())).encode()
            if "schema_migrations" in sql:
                if db not in self.versions:
                    raise dbsafety.SafetyError("relation does not exist")
                return "\n".join(self.versions[db]).encode()
        raise AssertionError(f"unexpected command {args}")

    def sql_statements(self):
        return [c[c.index("-c") + 1] for c in self.calls if c[0] == "exec" and "-c" in c]

    def restore_targets(self):
        return [c[c.index("-d") + 1] for c in self.calls if "pg_restore" in c and "-d" in c]


@pytest.fixture
def env(tmp_path, monkeypatch):
    root = tmp_path / "backups"
    root.mkdir()
    migrations = tmp_path / "migrations"
    (migrations / "down").mkdir(parents=True)
    for m in ("0001_a", "0002_b"):
        (migrations / f"{m}.sql").write_text("-- test")
    (migrations / "down" / "0002_b.down.sql").write_text("-- never applied")
    monkeypatch.setattr(dbsafety, "BACKUP_ROOT", root)
    monkeypatch.setattr(dbsafety, "MIGRATIONS_DIR", migrations)
    fake = FakeDocker()
    real = dbsafety.ROOT / "backups"
    before = sorted(p.name for p in real.iterdir()) if real.exists() else []
    yield fake, dbsafety.Pg(run=fake), root
    after = sorted(p.name for p in real.iterdir()) if real.exists() else []
    assert after == before, "a test wrote into the project's real backups/ directory"


def never_compose_or_lifecycle(fake):
    for c in fake.calls:
        assert c[0] in ("inspect", "exec"), c   # no compose / start / stop / restart / rm


def test_backup_writes_verified_manifest(env):
    fake, pg, root = env
    out = dbsafety.backup(pg, now=NOW)
    assert out.parent == root and out.name == "db-20261109-140000"
    m = json.loads((out / "MANIFEST.json").read_text())
    assert m["databases"]["store_a"]["tables"] == {"orders": 6, "products": 10, "schema_migrations": 3}
    assert m["databases"]["store_b"]["sha256"] == dbsafety.sha256((out / "store_b.dump").read_bytes())
    assert oct((out / "store_a.dump").stat().st_mode & 0o777) == "0o600"
    never_compose_or_lifecycle(fake)
    assert not any(s.startswith(("CREATE", "DROP", "INSERT", "UPDATE", "DELETE", "ALTER")) for s in fake.sql_statements())


def test_backup_refuses_when_container_unhealthy(env):
    fake, pg, root = env
    fake.healthy = False
    with pytest.raises(dbsafety.SafetyError, match="not running and healthy"):
        dbsafety.backup(pg, now=NOW)
    assert all(c[0] == "inspect" for c in fake.calls) and not list(root.iterdir())


def test_backup_refuses_unknown_database_names(env):
    _, pg, _ = env
    with pytest.raises(dbsafety.SafetyError, match="unknown database"):
        dbsafety.backup(pg, dbs=("postgres",), now=NOW)


def test_backup_detects_data_changing_during_the_dump(env):
    fake, pg, _ = env
    fake.mutate_after_dump = "store_b"
    with pytest.raises(dbsafety.SafetyError, match="row counts differ"):
        dbsafety.backup(pg, now=NOW)


def test_verify_detects_a_corrupted_backup(env):
    _, pg, _ = env
    out = dbsafety.backup(pg, now=NOW)
    (out / "store_a.dump").write_bytes(b"tampered")
    with pytest.raises(dbsafety.SafetyError, match="checksum mismatch"):
        dbsafety.verify(pg, out)


def test_restore_check_needs_explicit_confirmation(env):
    fake, pg, _ = env
    out = dbsafety.backup(pg, now=NOW)
    before = len(fake.calls)
    with pytest.raises(dbsafety.SafetyError, match="--confirm"):
        dbsafety.restore_check(pg, out, confirm=False)
    assert len(fake.calls) == before


def test_restore_check_uses_only_scratch_databases_and_cleans_up(env):
    fake, pg, _ = env
    out = dbsafety.backup(pg, now=NOW)
    results = dbsafety.restore_check(pg, out, confirm=True, now=NOW)
    assert set(results) == {"store_a", "store_b"} and all(r.startswith("OK") for r in results.values())
    assert fake.restore_targets() == ["store_a_restorecheck_20261109_140000", "store_b_restorecheck_20261109_140000"]
    for s in fake.sql_statements():
        if s.startswith(("CREATE DATABASE", "DROP DATABASE")):
            assert "_restorecheck_" in s, s
    assert not any("_restorecheck_" in d for d in fake.dbs)          # scratch databases dropped
    assert fake.dbs["store_a"] == {"products": 10, "orders": 6, "schema_migrations": 3}   # originals untouched
    never_compose_or_lifecycle(fake)


def test_restore_check_never_restores_an_unverified_backup(env):
    fake, pg, _ = env
    out = dbsafety.backup(pg, now=NOW)
    (out / "store_b.dump").write_bytes(b"tampered")
    with pytest.raises(dbsafety.SafetyError, match="checksum"):
        dbsafety.restore_check(pg, out, confirm=True, now=NOW)
    assert not any(s.startswith("CREATE DATABASE") for s in fake.sql_statements())


def test_restore_check_drops_scratch_even_when_counts_mismatch(env, monkeypatch):
    fake, pg, _ = env
    out = dbsafety.backup(pg, now=NOW)
    real = pg.table_counts
    monkeypatch.setattr(pg, "table_counts", lambda db: {"wrong": 1} if "_restorecheck_" in db else real(db))
    with pytest.raises(dbsafety.SafetyError, match="restored row counts differ"):
        dbsafety.restore_check(pg, out, confirm=True, now=NOW)
    assert not any("_restorecheck_" in d for d in fake.dbs)


@pytest.mark.parametrize("name", ["store_a", "store_b", "postgres", "store_a_restorecheck", "x_restorecheck_20261109_140000"])
def test_scratch_guard_rejects_anything_but_scratch_names(name):
    with pytest.raises(dbsafety.SafetyError):
        dbsafety._guard_scratch(name, {"store_a", "store_b", "postgres"})


def test_backup_dir_must_be_inside_backups(env, tmp_path):
    _, pg, _ = env
    with pytest.raises(dbsafety.SafetyError, match="inside backups"):
        dbsafety.verify(pg, tmp_path)


def test_precheck_ready_with_recent_backup(env):
    _, pg, _ = env
    dbsafety.backup(pg, now=NOW)
    assert dbsafety.precheck(pg, now=NOW + dt.timedelta(hours=1)) == []


def test_precheck_flags_version_mismatch_stale_or_missing_backup(env):
    fake, pg, _ = env
    assert any("no backup" in p for p in dbsafety.precheck(pg, now=NOW))
    dbsafety.backup(pg, now=NOW)
    assert any("h old" in p for p in dbsafety.precheck(pg, now=NOW + dt.timedelta(hours=30)))
    fake.versions["store_b"] = ["0001_a"]                       # one store lagging
    assert any("different migration versions" in p for p in dbsafety.precheck(pg, now=NOW))


def test_precheck_flags_unreachable_store(env):
    fake, pg, _ = env
    dbsafety.backup(pg, now=NOW)
    del fake.versions["store_a"]
    assert any("store_a: not reachable" in p for p in dbsafety.precheck(pg, now=NOW))


def test_down_scripts_are_never_treated_as_migrations(env):
    assert dbsafety.available_migrations() == ["0001_a", "0002_b"]


def test_backup_script_is_a_thin_wrapper_with_no_docker_lifecycle():
    sh = (Path(__file__).resolve().parents[1] / "backup_db.sh").read_text()
    code = [ln for ln in sh.splitlines() if ln.strip() and not ln.lstrip().startswith("#")]
    assert not [ln for ln in code if "docker" in ln or "curl" in ln or "rclone" in ln or "Drive" in ln]


def test_migration_runner_never_picks_up_down_scripts():
    root = Path(__file__).resolve().parents[2] / "backend" / "migrations"
    applied_by_runner = sorted(p.stem for p in root.glob("*.sql"))          # exactly what app/migrate.py iterates
    assert applied_by_runner and not any("down" in v for v in applied_by_runner)
    for down in (root / "down").glob("*.down.sql"):
        assert down.name.split(".")[0] in applied_by_runner, f"down script without a matching migration: {down.name}"
        assert "NEVER applied automatically" in down.read_text()
