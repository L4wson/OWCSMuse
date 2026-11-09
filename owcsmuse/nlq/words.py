"""The words of a question that are never a name on their own, in one closed list.

Names used to be what was left of a question once the words the parser recognised were removed, and every extractor
(a subject, a team in front of "player", the sides of a versus, a ban question's team) kept its own short list of words
to remove. A word on no list became part of a name: "highest kd of any player" ranked Anyones Legend's players without
a word about it, "best kd among players" refused because no team is called "among", and "Dallas Fuel record in 2026 NA
stage 3" asked which "dallas fuel na". Each earlier fix ("per 10", Students of the Game's "of", "partner team player")
added one word to one list (2026-11-05).

This list is closed: function words (determiners and quantifiers, pronouns, prepositions, conjunctions, auxiliaries,
question words), the words that rank or ask, and the question's own vocabulary (regions, stages, periods, roles, the
nouns a question counts). A name is a run of words not on it, with words on it allowed inside (Students of the Game);
a run made only of words on it is never a name. A real name that begins or ends with one ("All Gamers Global", "The
Kafe") is kept whole when the question spells it exactly (`KnownNames`), never trimmed into another name.
"""

from __future__ import annotations

import re
from typing import Iterable, Optional

from ..resolve import fold

DETERMINERS = {"a", "an", "the", "this", "that", "these", "those", "my", "your", "his", "her", "its", "our", "their",
               "any", "all", "every", "each", "some", "both", "either", "neither", "other", "another", "no", "none",
               "only", "just", "whole", "entire", "same", "such", "own", "several", "many", "much", "more", "less",
               "few", "fewer", "lots", "lot", "plenty", "enough", "certain", "various", "whichever", "whatever"}
PRONOUNS = {"anyone", "anybody", "everyone", "everybody", "someone", "somebody", "noone", "nobody", "anything",
            "everything", "something", "nothing", "i", "me", "you", "he", "him", "she", "it", "we", "us", "they", "them",
            "who", "whom", "whose", "which", "what", "one", "ones", "there", "here", "itself", "themselves"}
PREPOSITIONS = {"of", "in", "on", "at", "by", "for", "from", "to", "with", "without", "among", "amongst", "between",
                "across", "against", "vs", "versus", "v", "during", "over", "under", "into", "within", "throughout",
                "about", "per", "than", "as", "since", "until", "after", "before", "out"}
CONJUNCTIONS = {"and", "or", "but", "nor", "so", "if", "when", "while", "whether"}
AUXILIARIES = {"is", "was", "are", "were", "be", "been", "being", "do", "does", "did", "done", "has", "have", "had",
               "having", "can", "could", "will", "would", "should", "may", "might", "must", "get", "gets", "got",
               "show", "tell", "give", "list", "find", "see", "want", "know", "please"}
QUESTION_WORDS = {"how", "why", "where", "whats", "what's", "who's", "whos"}
# the verbs a question asks with ("how did X fare", "what did X average", "X played")
VERBS = {"play", "plays", "played", "playing", "go", "goes", "went", "gone", "fare", "fared", "perform", "performed",
         "score", "scored", "record", "recorded", "average", "averaged", "deal", "dealt", "heal", "healed", "die",
         "died", "post", "posted", "put", "finish", "finished", "place", "placed", "end", "ended", "rank", "do",
         "lose", "beat", "faced", "face", "met", "meet"}
NUMBER_WORDS = {"two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "fifteen", "twenty", "fifty"}
ADVERBS = {"never", "not", "always", "often", "frequently", "rarely", "usually", "times", "time", "again", "already",
           "together", "only", "ago"}
RANKING = {"most", "least", "fewest", "top", "bottom", "best", "worst", "highest", "lowest", "high", "low", "max",
           "maximum", "min", "minimum", "average", "avg", "mean", "total", "overall", "ever", "all-time", "alltime",
           "leader", "leaders", "leading", "leaderboard", "ranking", "rank", "ranked", "number", "count", "rate",
           "percentage", "ratio", "stats", "stat", "numbers", "record", "standings", "results", "result", "so", "far",
           "currently", "now", "still", "also", "even", "really", "very"}
# the things a question counts or slices by: never a name on their own
# "team" alone is no name, but it begins many ("Team Liquid") and "team twisted minds" resolves through the word: the
# extractors reject it alone (parser._clean_name) rather than trim it. "game" ends one (Students of the Game) and asks
# nothing a metric phrase does not already ("games played"), so it is not listed either.
VOCABULARY = {"player", "players", "teams", "org", "orgs", "organisation", "organization", "map", "maps",
              "mode", "modes", "series", "match", "matches", "season", "seasons", "year", "years",
              "stage", "stages", "playoff", "playoffs", "regular", "event", "events", "tournament", "tournaments",
              "tank", "tanks", "dps", "damage", "support", "supports", "healer", "healers", "role", "roles",
              "hero", "heroes", "ban", "bans", "banned", "banning", "pick", "picks", "kd", "kills", "deaths",
              "na", "emea", "eu", "europe", "european", "north", "american", "america", "international", "korea",
              "korean", "south", "owcs", "last", "previous", "current", "next", "won", "lost", "win", "wins", "losses"}

LISTED = (DETERMINERS | PRONOUNS | PREPOSITIONS | CONJUNCTIONS | AUXILIARIES | QUESTION_WORDS | ADVERBS | RANKING
          | VOCABULARY | VERBS | NUMBER_WORDS)

_YEAR = re.compile(r"^(?:19|20)\d\d$")
_NUMBER = re.compile(r"^\d{1,3}$")


def listed(word: str) -> bool:
    """A word that is never a name on its own: on the list, a year, or a small number ("top 5")."""
    w = word.lower().strip("'")
    return w in LISTED or bool(_YEAR.match(w)) or bool(_NUMBER.match(w))


def only_listed(text: Optional[str]) -> bool:
    """True when every word of `text` is on the list: "any", "among all", "the top 5". Never a name."""
    words = fold(text).split()
    return bool(words) and all(listed(w) for w in words)


class KnownNames:
    """The names the warehouse holds, folded, so a name that begins or ends with a listed word ("All Gamers Global",
    "The Kafe", "Team Liquid") is kept whole when a question spells it. Empty means: trim by the list alone."""

    def __init__(self, names: Iterable[str] = ()) -> None:
        self.folded = {f for f in (fold(n) for n in names) if f}

    def __bool__(self) -> bool:
        return bool(self.folded)

    def __contains__(self, text: str) -> bool:
        return fold(text) in self.folded

    def spans(self, text: str) -> list[tuple[int, int]]:
        """(start, end) of every name of two words or more spelled out in `text`, longest first and not overlapping, so
        the filters can be read around it: "GK EMEA" keeps its region word, "Students of the Game" its "of the"."""
        if not self.folded:
            return []
        toks = [(m.start(), m.end()) for m in re.finditer(r"\S+", text)]
        found: list[tuple[int, int]] = []
        for size in range(len(toks), 1, -1):
            for i in range(len(toks) - size + 1):
                a, b = toks[i][0], toks[i + size - 1][1]
                if any(a < e and s < b for s, e in found):
                    continue
                piece = text[a:b].strip(" ?.,!\"")
                if fold(piece) in self.folded and not only_listed(piece):
                    found.append((a, b))
        return found


NO_NAMES = KnownNames()


def known_span(words: list[str], known: KnownNames = NO_NAMES) -> Optional[str]:
    """The longest run of `words` that is a name the warehouse holds, or None: the whole run even when every word of it
    is listed ("someone"), otherwise never a run of listed words alone ("all" inside "highest kd of all")."""
    words = [w for w in words if w]
    if not known or not words:
        return None
    if " ".join(words) in known:
        return " ".join(words)
    for size in range(len(words) - 1, 0, -1):
        for i in range(len(words) - size + 1):
            span = " ".join(words[i:i + size])
            if span in known and not only_listed(span):
                return span
    return None


def name_in(words: list[str], known: KnownNames = NO_NAMES) -> Optional[str]:
    """The name in a run of words, or None.

    A known name spelled out in the run wins, longest first, even when it begins or ends with a listed word ("all
    gamers global"), unless it is listed words alone - except when the whole run is that name ("someone", a player:
    "Someone record"). Otherwise the run is trimmed of listed words at both ends; what is left is the name when it has a
    word not on the list. Words on the list stay inside a name ("students of the game").
    """
    words = [w for w in words if w]
    span = known_span(words, known)
    if span:
        return span
    while words and listed(words[0]):
        words.pop(0)
    while words and listed(words[-1]):
        words.pop()
    return " ".join(words) if words else None
