"""decisions_loaded's reload hints name commands that exist: a hint naming a wrong command (`aliases load` for
`alias load`) sends whoever reads a failing check to an error instead of the fix."""

import argparse

from owcsmuse.cli import build_parser
from owcsmuse.decisions_loaded import LOADERS


def _resolves(parser: argparse.ArgumentParser, words: list[str]) -> bool:
    for w in words:
        subs = [a for a in parser._actions if isinstance(a, argparse._SubParsersAction)]
        if not subs:
            return False                 # more words than there are subcommand levels
        if w not in subs[0].choices:
            return False
        parser = subs[0].choices[w]
    # the path must end at a leaf command, not a group that still wants a subcommand
    return not [a for a in parser._actions if isinstance(a, argparse._SubParsersAction) and a.required]


def test_every_reload_hint_is_a_real_command():
    for file, hint in LOADERS.items():
        for cmd in hint.split(", then "):
            words = cmd.split()
            assert words[:3] == ["python", "-m", "owcsmuse"], (file, cmd)
            assert _resolves(build_parser(), words[3:]), f"{file}: '{cmd}' is not a command"
