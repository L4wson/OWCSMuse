"""The test database is always on this machine (tests/db_guard.py)."""

from __future__ import annotations

import pytest

from db_guard import remote_hosts, require_local


@pytest.mark.parametrize("url", [
    "postgresql://owcs:owcs@localhost:5432/owcsmuse",
    "postgresql://postgres:postgres@127.0.0.1:5432/owcs",
    "postgresql://u:p@[::1]:5432/db",
    "postgresql:///owcsmuse?host=/var/run/postgresql",
    "host=localhost dbname=owcs",
    None,
])
def test_a_local_database_is_allowed(url):
    require_local(url)


@pytest.mark.parametrize("url", [
    "postgresql://postgres.x:pw@aws-0-us-west-2.pooler.supabase.com:5432/postgres",   # Supabase
    "postgresql://u:p@db.example.org:5432/owcs",                                      # anyone else's
    "postgresql://u:p@10.0.0.5:5432/owcs",                                            # a private address is still not here
    "host=localhost,db.example.org dbname=owcs",                                      # any remote host in a list
])
def test_any_remote_database_is_refused(url):
    assert remote_hosts(url)
    with pytest.raises(RuntimeError, match="not this machine"):
        require_local(url)


def test_pghost_counts_when_the_url_names_no_host(monkeypatch):
    monkeypatch.setenv("PGHOST", "db.example.org")
    with pytest.raises(RuntimeError):
        require_local("postgresql:///owcs")
