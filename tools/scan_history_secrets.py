"""Read-only scan of the whole git history for secrets, run before a repository goes public.

    python tools/scan_history_secrets.py

Reads every commit reachable from any branch, tag, stash or reflog entry (added AND removed lines, merge diffs
included, commit messages included) and looks for:

  * the exact values of the secrets in this machine's .env (FACEIT key, database URL and its password, Liquipedia key),
    which is the check that cannot miss the thing that matters;
  * well-known token shapes (GitHub, Anthropic/OpenAI-style, AWS), database URLs with an inline password, Supabase
    hosts and project refs, Authorization headers with a value, long opaque tokens;
  * committed files that should never be (.env, keys, certificates);
  * author and committer emails other than GitHub no-reply addresses.

It never prints a secret: a finding shows the file, the commit, what kind of thing it is, and the first four characters.
It changes nothing: no rewrite, no fetch, no checkout. Exit status 1 when anything is found.
"""

from __future__ import annotations

import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent

SHAPES: list[tuple[str, re.Pattern[str]]] = [
    ("github token", re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{30,}\b")),
    ("github fine-grained token", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b")),
    ("anthropic/openai-style key", re.compile(r"\bsk-(?:ant-)?[A-Za-z0-9_\-]{20,}\b")),
    ("aws access key id", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("database url with inline password", re.compile(r"\bpostgres(?:ql)?://[^\s'\"/:@]+:[^\s'\"@/]{3,}@[^\s'\"]+", re.I)),
    ("supabase host", re.compile(r"[a-z0-9\-]+\.(?:pooler\.)?supabase\.(?:co|com)\b", re.I)),
    ("authorization header with a value", re.compile(r"authorization['\"]?\s*[:=]\s*['\"]?(?:apikey|bearer|token)\s+[A-Za-z0-9\-_\.=]{16,}", re.I)),
    ("key assignment with a long value", re.compile(r"\b[A-Z_]*(?:API_?KEY|SECRET|TOKEN|PASSWORD)[A-Z_]*\s*=\s*['\"]?[A-Za-z0-9\-_/+=]{20,}")),
    ("long opaque token (100+ chars)", re.compile(r"(?<![A-Za-z0-9/+_\-])[A-Za-z0-9]{100,}(?![A-Za-z0-9/+_\-])")),
]
SUSPECT_PATHS = re.compile(r"(^|/)(\.env(\.(?!example$)[^/]*)?|.*\.pem|.*\.key|.*\.p12|.*\.pfx|id_rsa[^/]*|credentials(\.json)?)$")
NOREPLY = re.compile(r"@users\.noreply\.github\.com$", re.I)


def load_env_secrets() -> dict[str, str]:
    """Secrets worth an exact search: every non-empty value in .env except the obviously non-secret ones."""
    out: dict[str, str] = {}
    env = ROOT / ".env"
    if not env.exists():
        return out
    for line in env.read_text(encoding="utf-8").splitlines():
        if "=" not in line or line.lstrip().startswith("#"):
            continue
        name, value = line.split("=", 1)
        value = value.strip().strip("\"'")
        if len(value) >= 8:
            out[name.strip()] = value
            if "://" in value:                      # a URL: search for its password and host separately as well
                parsed = urlparse(value)
                if parsed.password:
                    out[f"{name.strip()} (password)"] = parsed.password
                if parsed.hostname:
                    out[f"{name.strip()} (host)"] = parsed.hostname
                if parsed.username and "." in parsed.username:
                    out[f"{name.strip()} (username / project ref)"] = parsed.username
    return out


def mask(s: str) -> str:
    return (s[:4] + "…") if len(s) > 4 else "…"


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, check=True).stdout.decode("utf-8", "replace")


def main() -> int:
    secrets = load_env_secrets()
    print(f"scanning for {len(secrets)} exact secret value(s) from .env ({', '.join(sorted(secrets))}) and "
          f"{len(SHAPES)} token shapes", file=sys.stderr)

    refs = git("for-each-ref", "--format=%(refname)").split()
    n_commits = len(git("rev-list", "--all", "--reflog").split())
    print(f"refs: {len(refs)} ({', '.join(r.replace('refs/', '') for r in refs)}); commits reachable incl. reflog: {n_commits}",
          file=sys.stderr)

    findings: dict[tuple[str, str, str], set[str]] = defaultdict(set)     # (kind, path, commit) -> masked evidence
    proc = subprocess.Popen(["git", "log", "--all", "--reflog", "-m", "-p", "-U0", "--no-color", "--no-textconv",
                             "--format=@@COMMIT %H%n@@AUTHOR %ae %ce%n@@MSG %B%n@@END"],
                            cwd=ROOT, stdout=subprocess.PIPE)
    commit, path, in_msg = "?", "(commit message)", False
    for raw in proc.stdout:                                      # type: ignore[union-attr]
        line = raw.decode("utf-8", "replace").rstrip("\n")
        if line.startswith("@@COMMIT "):
            commit, path, in_msg = line.split()[1][:10], "(commit message)", False
            continue
        if line.startswith("@@AUTHOR "):
            for email in line.split()[1:]:
                if email and not NOREPLY.search(email):
                    findings[("personal email in commit metadata", "(author/committer)", commit)].add(mask(email))
            continue
        if line.startswith("@@MSG "):
            in_msg = True
            line = line[len("@@MSG "):]
        elif line.startswith("@@END"):
            in_msg, path = False, "?"
            continue
        elif line.startswith("+++ b/"):
            path = line[6:]
            if SUSPECT_PATHS.search(path):
                findings[("file that should not be committed", path, commit)].add(path)
            continue
        elif line.startswith("--- ") or line.startswith("diff --git"):
            continue
        if not in_msg and line[:1] not in ("+", "-"):
            continue
        for name, value in secrets.items():
            if value in line:
                findings[(f"EXACT secret from .env: {name}", path, commit)].add(mask(value))
        for kind, pat in SHAPES:
            for m in pat.finditer(line):
                findings[(kind, path, commit)].add(mask(m.group(0)))

    if not findings:
        print("no findings")
        return 0
    by_kind: dict[str, list[tuple[str, str, set[str]]]] = defaultdict(list)
    for (kind, p, c), ev in findings.items():
        by_kind[kind].append((p, c, ev))
    for kind, items in sorted(by_kind.items()):
        print(f"\n{kind}: {len(items)} place(s)")
        for p, c, ev in sorted(items)[:25]:
            print(f"  {c}  {p}  [{', '.join(sorted(ev))}]")
        if len(items) > 25:
            print(f"  ... {len(items) - 25} more")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
