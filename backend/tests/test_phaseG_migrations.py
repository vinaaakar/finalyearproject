"""Phase G: the hardened migration runner. Everything runs in throwaway schemas inside the *_test databases
(search_path set per connection); the development databases are never touched."""

from __future__ import annotations

import uuid
from pathlib import Path
from urllib.parse import quote

import psycopg
import pytest

from app import migrate as m

OK1 = "CREATE TABLE widgets (id SERIAL PRIMARY KEY, name TEXT NOT NULL);\n"
OK2 = "ALTER TABLE widgets ADD COLUMN colour TEXT;\nCREATE TABLE gadgets (id SERIAL PRIMARY KEY);\n"


@pytest.fixture
def scratch(settings):
    """Two scratch schemas (one per store test database) and helpers."""
    schema = f"migtest_{uuid.uuid4().hex[:10]}"
    base = {s: settings.store_database_urls[s] for s in m.STORE_ORDER}
    assert all(m.db_name(u).endswith("_test") for u in base.values())
    for u in base.values():
        with psycopg.connect(u, autocommit=True) as c:
            c.execute(f"CREATE SCHEMA {schema}")
    sep = lambda u: "&" if "?" in u else "?"  # noqa: E731
    urls = {s: f"{u}{sep(u)}options={quote(f'-c search_path={schema}')}" for s, u in base.items()}

    def sql(store, statement, params=None):
        with psycopg.connect(urls[store], autocommit=True) as c:
            cur = c.execute(statement, params)
            return cur.fetchall() if cur.description else None

    yield urls, sql
    for u in base.values():
        with psycopg.connect(u, autocommit=True) as c:
            c.execute(f"DROP SCHEMA {schema} CASCADE")


def write(dir_: Path, files: dict[str, str]) -> Path:
    dir_.mkdir(exist_ok=True)
    for name, body in files.items():
        (dir_ / f"{name}.sql").write_text(body)
    return dir_


def versions(sql, store):
    return [r[0] for r in sql(store, "SELECT version FROM schema_migrations ORDER BY 1")]


# ---- lint ----------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("body, problem", [
    ("BEGIN;\nCREATE TABLE x (id int);\nCOMMIT;", "transaction control"),
    ("CREATE INDEX CONCURRENTLY i ON t (c);", "cannot run in a transaction"),
    ("VACUUM t;", "cannot run in a transaction"),
    ("DROP TABLE customers;", "destructive statement"),
    ("ALTER TABLE orders DROP COLUMN total_cents;", "destructive statement"),
    ("TRUNCATE orders;", "destructive statement"),
    ("DELETE FROM orders WHERE id = 1;", "destructive statement"),
])
def test_lint_refuses_unsafe_statements(body, problem):
    assert problem in m.lint_migration(body)


@pytest.mark.parametrize("body", [
    "DO $$ BEGIN IF true THEN RAISE NOTICE 'x'; END IF; END $$;",
    "-- we never DROP TABLE or TRUNCATE here\nCREATE TABLE y (id int);",
    "INSERT INTO notes VALUES ('please DELETE FROM the list');",
    "ALTER TABLE orders DROP CONSTRAINT orders_status_check;",     # constraint changes are not data loss
])
def test_lint_allows_safe_text(body):
    assert m.lint_migration(body) == []


def test_real_migrations_pass_lint_and_down_scripts_would_not():
    files = m.load_files()
    assert list(files)[:5] == ["0001_initial_schema", "0002_commerce", "0003_policy_translations", "0004_policy_truth", "0005_fulfilment"]
    for p in (m.MIGRATIONS_DIR / "down").glob("*.sql"):
        assert m.lint_migration(p.read_text())          # down scripts are destructive by nature and never auto-applied


def test_lint_failure_refuses_the_whole_run(tmp_path, scratch):
    urls, sql = scratch
    d = write(tmp_path / "mig", {"0001_a": OK1, "0002_bad": "BEGIN; CREATE TABLE z (id int); COMMIT;"})
    with pytest.raises(m.MigrationError, match="lint"):
        m.run(urls, apply=True, directory=d)
    assert sql("store-a", "SELECT to_regclass('widgets')")[0][0] is None


# ---- planning (pure) -----------------------------------------------------------------------------------------------
def test_plan_detects_mismatch_missing_null_divergence_and_out_of_order():
    files = {"0001": "aaa", "0002": "bbb", "0003": "ccc"}
    assert m.make_plan({"a": {"0001": "aaa"}, "b": {"0001": "aaa"}}, files).pending == {"a": ["0002", "0003"], "b": ["0002", "0003"]}
    p = m.make_plan({"a": {"0001": "xxx"}, "b": {"0001": "aaa"}}, files)
    assert any("modified after it was applied" in x for x in p.problems)
    assert any("missing from this checkout" in x for x in m.make_plan({"a": {"0009": "q"}, "b": {"0009": "q"}}, files).problems)
    assert any("no recorded checksum" in x for x in m.make_plan({"a": {"0001": None}, "b": {"0001": "aaa"}}, files).problems)
    div = m.make_plan({"a": {"0001": "aaa", "0002": "bbb"}, "b": {"0001": "aaa"}}, files)
    assert any("different versions" in x for x in div.problems)
    rep = m.make_plan({"a": {"0001": "aaa", "0002": "bbb"}, "b": {"0001": "aaa"}}, files, repair=True)
    assert rep.ok and rep.pending == {"a": [], "b": ["0002"]}       # never anything newer than the other store
    gap = m.make_plan({"a": {"0001": "aaa", "0003": "ccc"}, "b": {"0001": "aaa", "0003": "ccc"}}, files)
    assert any("out-of-order" in x for x in gap.problems)


# ---- applying ------------------------------------------------------------------------------------------------------
def test_applies_in_lockstep_with_checksums(tmp_path, scratch):
    urls, sql = scratch
    d = write(tmp_path / "mig", {"0001_a": OK1, "0002_b": OK2})
    report = m.run(urls, apply=True, directory=d)
    assert [(r["store"], r["version"], r["status"]) for r in report["results"]] == [
        ("store-a", "0001_a", "ok"), ("store-b", "0001_a", "ok"), ("store-a", "0002_b", "ok"), ("store-b", "0002_b", "ok")]
    for store in m.STORE_ORDER:
        rows = sql(store, "SELECT version, checksum, applied_by FROM schema_migrations ORDER BY 1")
        assert [r[1] for r in rows] == [m.file_checksum(d / "0001_a.sql"), m.file_checksum(d / "0002_b.sql")]
        assert all(r[2].startswith("avc-migrate@") for r in rows)
    again = m.run(urls, apply=True, directory=d)
    assert again["results"] == [] and again["pending"] == {"store-a": [], "store-b": []}


def test_status_and_plan_write_nothing(tmp_path, scratch):
    urls, sql = scratch
    d = write(tmp_path / "mig", {"0001_a": OK1})
    plan = m.run(urls, apply=False, directory=d)
    assert plan["pending"] == {"store-a": ["0001_a"], "store-b": ["0001_a"]}
    assert sql("store-a", "SELECT to_regclass('schema_migrations')")[0][0] is None     # plan created nothing
    st = m.status(urls, directory=d)
    assert st["stores"]["store-a"]["pending"] == ["0001_a"] and st["stores"]["store-a"]["lock_holder"] is None
    assert sql("store-b", "SELECT to_regclass('schema_migrations')")[0][0] is None


def test_edited_applied_migration_is_refused(tmp_path, scratch):
    urls, sql = scratch
    d = write(tmp_path / "mig", {"0001_a": OK1})
    m.run(urls, apply=True, directory=d)
    (d / "0001_a.sql").write_text(OK1 + "\n")            # even a whitespace change counts
    with pytest.raises(m.MigrationError, match="modified after it was applied"):
        m.run(urls, apply=True, directory=write(d, {"0002_b": OK2}))
    assert sql("store-a", "SELECT to_regclass('gadgets')")[0][0] is None


def test_failure_on_store_b_leaves_one_version_apart_then_repair(tmp_path, scratch):
    urls, sql = scratch
    d = write(tmp_path / "mig", {"0001_a": OK1})
    m.run(urls, apply=True, directory=d)
    sql("store-b", "CREATE TABLE gadgets (x int)")       # makes 0002 fail on Store B only
    write(d, {"0002_b": OK2})
    with pytest.raises(m.MigrationError, match=r"store-b: 0002_b failed .*rolled back"):
        m.run(urls, apply=True, directory=d)
    assert versions(sql, "store-a") == ["0001_a", "0002_b"] and versions(sql, "store-b") == ["0001_a"]
    assert sql("store-b", "SELECT count(*) FROM information_schema.columns WHERE table_schema = current_schema() "
                          "AND table_name = 'widgets' AND column_name = 'colour'")[0][0] == 0      # B's 0002 fully rolled back
    with pytest.raises(m.MigrationError, match="different versions"):
        m.run(urls, apply=True, directory=write(d, {"0003_c": "CREATE TABLE more (id int);"}))
    (d / "0003_c.sql").unlink()
    sql("store-b", "ALTER TABLE gadgets RENAME TO gadgets_old")   # the operator fixes the cause
    report = m.run(urls, apply=False, repair=True, directory=d)
    assert [(r["store"], r["version"]) for r in report["results"]] == [("store-b", "0002_b")]
    assert versions(sql, "store-a") == versions(sql, "store-b") == ["0001_a", "0002_b"]


def test_concurrent_runner_is_refused_and_names_the_holder(tmp_path, scratch, settings):
    urls, sql = scratch
    d = write(tmp_path / "mig", {"0001_a": OK1})
    with psycopg.connect(settings.store_database_urls["store-a"], autocommit=True, application_name="other-runner") as holder:
        holder.execute("SELECT pg_advisory_lock(%s)", [m.LOCK_KEY])
        with pytest.raises(m.MigrationError, match=r"holds the lock: pid \d+ \(other-runner"):
            m.run(urls, apply=True, directory=d, lock_timeout_s=1)
        assert m.status(urls, directory=d)["stores"]["store-a"]["lock_holder"].startswith("pid ")
    assert sql("store-a", "SELECT to_regclass('widgets')")[0][0] is None
    assert m.run(urls, apply=True, directory=d)["results"]          # lock released → works


def test_lock_timeout_aborts_cleanly_instead_of_queueing(tmp_path, scratch):
    urls, sql = scratch
    d = write(tmp_path / "mig", {"0001_a": OK1})
    m.run(urls, apply=True, directory=d)
    write(d, {"0002_b": OK2})
    with psycopg.connect(urls["store-a"]) as blocker:              # an open transaction holding a table lock
        blocker.execute("LOCK TABLE widgets IN ACCESS SHARE MODE")
        with pytest.raises(m.MigrationError, match="LockNotAvailable"):
            m.run(urls, apply=True, directory=d, migration_lock_timeout="300ms")
        blocker.rollback()
    assert versions(sql, "store-a") == ["0001_a"] and versions(sql, "store-b") == ["0001_a"]


def test_non_test_databases_require_the_precheck(tmp_path, scratch, monkeypatch):
    urls, sql = scratch
    d = write(tmp_path / "mig", {"0001_a": OK1})
    m.run(urls, apply=True, directory=d)                             # not fresh any more
    write(d, {"0002_b": OK2})
    monkeypatch.setattr(m, "db_name", lambda url: "store_a")         # pretend these are development databases
    calls = []
    with pytest.raises(m.MigrationError, match="precheck failed: no verified backup"):
        m.run(urls, apply=True, directory=d, precheck=lambda b, age: calls.append(b) or ["no verified backup"])
    assert calls == [None] and versions(sql, "store-a") == ["0001_a"]
    assert m.default_precheck(None, 24) == ["--backup backups/db-<timestamp> is required (create one with scripts/backup_db.sh)"]


def test_fresh_install_needs_no_backup(tmp_path, scratch, monkeypatch):
    urls, sql = scratch
    monkeypatch.setattr(m, "db_name", lambda url: "store_a")
    report = m.run(urls, apply=True, directory=write(tmp_path / "mig", {"0001_a": OK1}),
                   precheck=lambda *a: pytest.fail("precheck must not be needed for empty databases"), write_log=False)
    assert report["fresh_install"] is True and len(report["results"]) == 2


def test_real_migrations_build_a_fresh_store(scratch):
    urls, sql = scratch
    report = m.run(urls, apply=True)
    assert [r["version"] for r in report["results"] if r["store"] == "store-a"] == list(m.load_files())
    assert sql("store-a", "SELECT to_regclass('order_status_history')")[0][0] is not None


def test_adopt_records_checksums_only_for_committed_identical_files(tmp_path, scratch):
    urls, sql = scratch
    d = write(tmp_path / "mig", {"0001_a": OK1})
    m.run(urls, apply=True, directory=d)
    for s in m.STORE_ORDER:
        sql(s, "UPDATE schema_migrations SET checksum = NULL")     # as rows from before checksums existed
    with pytest.raises(m.MigrationError, match="no recorded checksum"):
        m.run(urls, apply=True, directory=d)
    with pytest.raises(m.MigrationError, match="differs from its committed version"):
        m.adopt(urls, directory=d, git_show=lambda rel: b"something else")
    assert sql("store-a", "SELECT checksum FROM schema_migrations")[0][0] is None
    assert m.adopt(urls, directory=d, git_show=lambda rel: (d / Path(rel).name).read_bytes()) == {"store-a": ["0001_a"], "store-b": ["0001_a"]}
    assert m.run(urls, apply=True, directory=d)["results"] == []


def test_migrate_database_refuses_non_test_databases():
    with pytest.raises(m.MigrationError, match="only"):
        m.migrate_database("postgresql://u:p@127.0.0.1:5433/store_a")


def test_api_refuses_to_start_on_an_old_schema(scratch, settings):
    import dataclasses
    from app.main import create_app
    from fastapi.testclient import TestClient
    urls, sql = scratch                       # empty scratch schemas: every migration is pending
    app = create_app(dataclasses.replace(settings, store_database_urls=urls), llm=False)
    with pytest.raises(RuntimeError, match="database schema is behind this code"):
        with TestClient(app):
            pass
