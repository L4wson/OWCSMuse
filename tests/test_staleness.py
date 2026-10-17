"""A stale checkout stops before it touches the database, instead of answering from an old schema."""

import shutil
import subprocess

import pytest

from owcsmuse import staleness
from owcsmuse.staleness import StaleCheckout, commits_behind, guard, problems, unknown_migrations


@pytest.fixture
def migrations(tmp_path):
    d = tmp_path / "migrations"
    d.mkdir()
    for name in ("001_initial.sql", "002_scope.sql"):
        (d / name).write_text("-- x")
    return d


def test_a_database_migration_this_checkout_lacks_is_named(migrations):
    assert unknown_migrations(["001_initial.sql", "002_scope.sql", "003_new.sql"], migrations) == ["003_new.sql"]
    assert unknown_migrations(["001_initial.sql"], migrations) == []   # behind the files is just pending


def test_current_checkout_has_no_problems(migrations):
    assert problems(applied=["001_initial.sql"], migrations_dir=migrations, behind=0) == []
    assert problems(applied=None, migrations_dir=migrations, behind=None) == []   # no database, no git


def test_stale_database_stops_the_command(migrations, monkeypatch):
    monkeypatch.delenv("OWCS_ALLOW_STALE", raising=False)
    with pytest.raises(StaleCheckout, match="1 migration"):
        guard(applied=["001_initial.sql", "025_competition_names.sql"], migrations_dir=migrations, behind=0)


def test_branch_behind_main_stops_the_command(migrations, monkeypatch):
    monkeypatch.delenv("OWCS_ALLOW_STALE", raising=False)
    with pytest.raises(StaleCheckout, match="85 commit"):
        guard(applied=[], migrations_dir=migrations, behind=85)


def test_allowed_runs_but_still_reports(migrations, monkeypatch):
    monkeypatch.setenv("OWCS_ALLOW_STALE", "1")
    found = guard(applied=["009_x.sql"], migrations_dir=migrations, behind=3)
    assert len(found) == 2


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_commits_behind_reads_the_remote_tracking_ref(tmp_path):
    def git(*a):
        subprocess.run(["git", "-C", str(tmp_path), *a], check=True, capture_output=True)
    git("init", "-q")
    git("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "one")
    git("update-ref", "refs/remotes/origin/main", "HEAD")
    assert commits_behind(repo=tmp_path) == 0
    git("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "two")
    git("update-ref", "refs/remotes/origin/main", "HEAD")
    git("reset", "-q", "--hard", "HEAD~1")
    assert commits_behind(repo=tmp_path) == 1


def test_no_git_checkout_is_not_a_problem(tmp_path):
    assert commits_behind(repo=tmp_path) is None   # an installed package or the Fly image


def test_cli_refuses_with_exit_3(monkeypatch, migrations):
    from owcsmuse import cli
    monkeypatch.delenv("OWCS_ALLOW_STALE", raising=False)
    monkeypatch.setattr(staleness, "commits_behind", lambda *a, **k: 12)
    monkeypatch.setattr(cli, "connect", lambda *a, **k: (_ for _ in ()).throw(OSError("no database here")))
    monkeypatch.setenv("DATABASE_URL", "postgresql://unused")
    assert cli.main(["status"]) == 3


def test_pending_is_the_other_direction(migrations):
    assert staleness.pending_migrations(["001_initial.sql"], migrations) == ["002_scope.sql"]


@pytest.mark.parametrize("command, pending, expected", [
    ("serve", True, 0),      # never refuse to serve: a rollback image must come up
    ("migrate", False, 0),   # a rollback image's release step has nothing to add
    ("migrate", True, 3),    # a stale branch adding its own migration to a newer schema
    ("status", False, 3),
])
def test_rollback_safe_commands(monkeypatch, migrations, command, pending, expected):
    from contextlib import contextmanager
    from owcsmuse import cli
    monkeypatch.delenv("OWCS_ALLOW_STALE", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql://unused")
    monkeypatch.setenv("OWCS_MIGRATIONS_DIR", str(migrations))
    applied = ["001_initial.sql", "099_newer.sql"] + ([] if pending else ["002_scope.sql"])
    monkeypatch.setattr(staleness, "commits_behind", lambda *a, **k: 0)
    monkeypatch.setattr(staleness, "applied_migrations", lambda conn: applied)

    @contextmanager
    def fake_connect(*a, **k):
        yield object()
    monkeypatch.setattr(cli, "connect", fake_connect)
    monkeypatch.setattr(cli, "cmd_serve", lambda a, s: 0)
    monkeypatch.setattr(cli, "cmd_migrate", lambda a, s: 0)
    monkeypatch.setattr(cli, "cmd_status", lambda a, s: 0)
    argv = {"serve": ["serve"], "migrate": ["migrate"], "status": ["status"]}[command]
    assert cli.main(argv) == expected
