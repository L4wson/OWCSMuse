"""Refuse to run against a database, or a branch, that is newer than this checkout.

A checkout that has fallen behind still connects, migrates, ingests and answers.
Nothing fails: the old code just reads a schema it predates and reports
plausible, wrong results. One session diagnosed against a branch 85 commits
behind origin/main for an afternoon this way - the database had migrations
025-043 that the checkout had never seen, and "nothing pending" was true of the
checkout's own files and meaningless for the database.

Two checks, both loud:

  * the database has applied a migration this checkout does not have
    (schema_migrations lists a version missing from migrations/) - the code is
    older than the schema it is about to read or write. No git needed, so it
    also holds for an installed package.
  * the working branch is behind origin/main, by the local remote-tracking ref
    (no network call: `git fetch` is what makes it current).

Either one stops the command. `--allow-stale` (or OWCS_ALLOW_STALE=1) runs it
anyway, for the rare deliberate case - checking out an old commit to reproduce
what production did - and still prints why it would have stopped.

Two commands only warn, so a rollback to an older image keeps working: `serve`,
and `migrate` when it has nothing of its own to apply. `migrate` still refuses
to add a stale checkout's migrations to a newer schema.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Iterable, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BASE_REF = "origin/main"


class StaleCheckout(RuntimeError):
    """This checkout is older than the database or the main branch it is about to work against."""


def unknown_migrations(applied: Iterable[str], migrations_dir: str | Path) -> list[str]:
    """Versions the database has applied that this checkout has no file for."""
    path = Path(migrations_dir)
    have = {p.name for p in path.glob("*.sql")} if path.exists() else set()
    return sorted(v for v in applied if v not in have)


def pending_migrations(applied: Iterable[str], migrations_dir: str | Path) -> list[str]:
    """This checkout's migration files the database has not applied."""
    path = Path(migrations_dir)
    done = set(applied)
    return sorted(p.name for p in path.glob("*.sql") if p.name not in done) if path.exists() else []


def applied_migrations(conn) -> list[str]:
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass('schema_migrations') IS NOT NULL AS present")
        if not cur.fetchone()["present"]:
            conn.rollback()
            return []
        cur.execute("SELECT version FROM schema_migrations")
        out = [r["version"] for r in cur.fetchall()]
    conn.rollback()
    return out


def commits_behind(ref: str = BASE_REF, repo: Path = PROJECT_ROOT) -> Optional[int]:
    """How many commits `ref` has that HEAD lacks; None when there is no git checkout or no such ref."""
    if not (repo / ".git").exists():
        return None
    try:
        out = subprocess.run(["git", "-C", str(repo), "rev-list", "--count", f"HEAD..{ref}"],
                             capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    try:
        return int(out.stdout.strip())
    except ValueError:
        return None


def problems(*, applied: Optional[Iterable[str]], migrations_dir: str | Path,
             behind: Optional[int], ref: str = BASE_REF) -> list[str]:
    """Why this checkout should not run, in plain words. Empty when it is current."""
    out: list[str] = []
    if applied is not None:
        unknown = unknown_migrations(applied, migrations_dir)
        if unknown:
            shown = ", ".join(unknown[:5]) + (f" and {len(unknown) - 5} more" if len(unknown) > 5 else "")
            out.append(f"the database has {len(unknown)} migration(s) this checkout does not: {shown}. "
                       "The code is older than the schema it would read and write.")
    if behind:
        out.append(f"this branch is {behind} commit(s) behind {ref}. Rebase or merge it before diagnosing "
                   f"anything against the database (run `git fetch` first if {ref} itself may be old).")
    return out


def allowed_stale(flag: bool = False) -> bool:
    return flag or os.environ.get("OWCS_ALLOW_STALE", "").strip().lower() in ("1", "true", "yes")


def guard(*, applied: Optional[Iterable[str]], migrations_dir: str | Path, behind: Optional[int],
          allow: bool = False, ref: str = BASE_REF) -> list[str]:
    """Raise StaleCheckout when the checkout is stale, unless allowed; return the problems either way."""
    found = problems(applied=applied, migrations_dir=migrations_dir, behind=behind, ref=ref)
    if found and not allowed_stale(allow):
        raise StaleCheckout("refusing to run a stale checkout:\n  - " + "\n  - ".join(found)
                            + "\n(--allow-stale or OWCS_ALLOW_STALE=1 runs it anyway)")
    return found
