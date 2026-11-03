"""Tests and test tools only ever touch a database on this machine.

Every database test drops and recreates scratch schemas, and the golden and fixture builders do the same. Pointed at a
remote database they build there: 39 `owcs_golden_*` / `owcs_test_*` / `owcs_fixture` schemas (170 MB, and 5,380
catalog objects) accumulated in production because earlier guidance said to point OWCS_TEST_DATABASE_URL at Supabase
(found 2026-11-03, with the project over its storage limit). That guidance was wrong, not the code: the rule is now
that a test database is local, whoever would host a remote one - so this allows local hosts, never blocklists a
provider.
"""

from __future__ import annotations

import ipaddress
import os
from typing import Optional

from psycopg.conninfo import conninfo_to_dict

LOCAL_NAMES = {"localhost"}


def _is_local(host: str) -> bool:
    if not host or host.startswith("/") or host.startswith("@"):     # a Unix socket directory (or abstract socket)
        return True
    if host.lower() in LOCAL_NAMES:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def remote_hosts(url: Optional[str]) -> list[str]:
    """The hosts in a connection string (or libpq's PGHOST/PGHOSTADDR when it names none) that are not this machine."""
    if not url:
        return []
    info = conninfo_to_dict(url)
    hosts = [h for key in ("host", "hostaddr") for h in (info.get(key) or "").split(",") if h]
    if not hosts:
        hosts = [h for key in ("PGHOST", "PGHOSTADDR") for h in (os.environ.get(key) or "").split(",") if h]
    return [h for h in hosts if not _is_local(h)]


def require_local(url: Optional[str], what: str = "OWCS_TEST_DATABASE_URL") -> None:
    """Refuse a database that is not on this machine, before anything connects to it."""
    remote = remote_hosts(url)
    if remote:
        raise RuntimeError(
            f"{what} points at {', '.join(remote)}, which is not this machine. Tests and test tools build and drop "
            "scratch schemas, so they only run against a local Postgres: `docker compose up -d db`, then "
            "postgresql://owcs:owcs@localhost:5432/owcsmuse.")
