"""CC-BY-SA attribution: every Liquipedia-sourced value carries the page it came from.

Liquipedia's data is licensed CC-BY-SA 3.0, and the API application committed to
crediting it. That commitment is only kept if the credit cannot be forgotten, so
it is a property of the value, not a step someone remembers at display time:

  * `Sourced` cannot be constructed without a Liquipedia page URL;
  * the tables that will hold Liquipedia-derived values carry a NOT NULL, checked
    `page_url` column (see migration 022's liquipedia_coverage, and Stage 1's tables);
  * an answer built from such values names those pages in `Answer.attribution`,
    which `attribution_block` builds and `render_lines` prints.

A page URL is derived from the record's own page name, never guessed: a value
whose page name is missing is refused rather than credited to a generic URL.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Generic, Iterable, Optional, TypeVar
from urllib.parse import quote

import psycopg

SITE = "https://liquipedia.net"
LICENSE = "CC-BY-SA 3.0"
LICENSE_URL = "https://creativecommons.org/licenses/by-sa/3.0/"
CREDIT = "Liquipedia"

T = TypeVar("T")


class MissingAttribution(ValueError):
    """A Liquipedia-sourced value was about to exist without the page it came from."""


def page_url(pagename: Optional[str], wiki: str = "overwatch") -> str:
    """The public Liquipedia URL of a page, from the page name the API returns.

    MediaWiki titles use underscores for spaces and keep '/' for subpages; anything else is percent-encoded.
    """
    if not pagename or not pagename.strip():
        raise MissingAttribution("a Liquipedia page name is required to attribute a value; none was given")
    title = pagename.strip().replace(" ", "_")
    return f"{SITE}/{wiki}/{quote(title, safe='/:_,()!*~-.')}"


@dataclass(frozen=True)
class Sourced(Generic[T]):
    """A value taken from Liquipedia, with the page it was taken from and the stored response it is in."""

    value: T
    page_url: str
    raw_id: Optional[int] = None          # the raw_payloads row holding the response
    retrieved_at: Optional[datetime] = None

    def __post_init__(self) -> None:
        if not (isinstance(self.page_url, str) and self.page_url.startswith(SITE + "/")):
            raise MissingAttribution(f"a Liquipedia-sourced value needs a {SITE}/... page URL, got {self.page_url!r}")


def attribution_block(urls: Iterable[str]) -> Optional[dict[str, Any]]:
    """What an answer built from Liquipedia values must carry, or None when it used none.

    Sorted and de-duplicated so the same answer always credits the same way.
    """
    pages = sorted({u for u in urls if u})
    for u in pages:
        if not u.startswith(SITE + "/"):
            raise MissingAttribution(f"not a Liquipedia page URL: {u!r}")
    if not pages:
        return None
    return {"source": CREDIT, "license": LICENSE, "license_url": LICENSE_URL, "pages": pages}


def answer_attribution(conn: psycopg.Connection, match_ids: Iterable[str]) -> Optional[dict[str, Any]]:
    """The attribution block for an answer, from the FACEIT match ids its rows actually named.

    A match only carries a page here when a value it contributed was Liquipedia's: a Stage 2 map (`match_rounds.
    source = 'liquipedia'`) or a Stage 2 date correction (`matches.date_source = 'liquipedia'`). A match FACEIT
    covers completely names no page, exactly like an answer that used no Liquipedia value at all.
    """
    ids = [m for m in dict.fromkeys(match_ids) if m]
    if not ids:
        return None
    # a Liquipedia-only series (Stage 3) is keyed `lp:<objectname>` and owes its page for everything
    lp_only = [m[3:] for m in ids if m.startswith("lp:")]
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT lm.page_url
              FROM liquipedia_links ll
              JOIN liquipedia_matches lm ON lm.objectname = ll.lp_objectname
             WHERE ll.faceit_match_id = ANY(%s)
               AND (
                    EXISTS (SELECT 1 FROM match_rounds r WHERE r.match_id = ll.faceit_match_id AND r.source = 'liquipedia')
                 OR EXISTS (SELECT 1 FROM matches m WHERE m.match_id = ll.faceit_match_id AND m.date_source = 'liquipedia')
               )
            UNION
            SELECT DISTINCT lm.page_url FROM liquipedia_matches lm WHERE lm.objectname = ANY(%s)
            """,
            (ids, lp_only),
        )
        urls = [r["page_url"] for r in cur.fetchall()]
    conn.commit()
    return attribution_block(urls)


def render_lines(block: Optional[dict[str, Any]]) -> list[str]:
    """The attribution as plain text lines, for the CLI; an answer with none renders nothing."""
    if not block:
        return []
    lines = [f"  source: {block['source']} ({block['license']}, {block['license_url']})"]
    lines += [f"    {u}" for u in block["pages"]]
    return lines
