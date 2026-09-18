"""Shareable slugs: deterministic, stable, and independent of how a question was typed."""

from owcsmuse.web import SLUG_LENGTH, Suggestion, normalize_question, slug_for


def test_the_same_question_always_gets_the_same_slug():
    assert slug_for("who had the most eliminations") == slug_for("who had the most eliminations")
    assert len(slug_for("x")) == SLUG_LENGTH


def test_typing_does_not_change_the_link():
    canonical = slug_for("Twisted Minds vs ENCE")
    for variant in ("twisted minds vs ence", "  Twisted   Minds vs ENCE  ", "TWISTED MINDS VS ENCE"):
        assert slug_for(variant) == canonical


def test_a_different_question_or_parser_is_a_different_link():
    assert slug_for("Twisted Minds vs ENCE") != slug_for("ENCE vs Twisted Minds")
    assert slug_for("a question") != slug_for("a question", parser="llm")


def test_slugs_are_url_safe():
    for question in ("who had the most eliminations in 2024?", "Ex Oblivione / Team Peps", "KSAA's kd"):
        slug = slug_for(question)
        assert slug.isascii() and all(c.isalnum() or c in "-_" for c in slug), slug


def test_normalizing_a_question_keeps_its_words():
    assert normalize_question("  Who   had  the MOST  ") == "who had the most"
    assert normalize_question("") == "" and normalize_question(None) == ""


def test_a_suggestion_carries_the_link_it_would_produce():
    s = Suggestion("Twisted Minds record", "Teams").as_dict()
    assert s == {"question": "Twisted Minds record", "group": "Teams", "slug": slug_for("Twisted Minds record")}
