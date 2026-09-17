import json
import os
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str):
    with open(FIXTURES / name, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def fx():
    return load_fixture


@pytest.fixture(scope="module")
def agg_db():
    """Scratch schema with the three fixture matches ingested and aggregates refreshed (needs OWCS_TEST_DATABASE_URL)."""
    db_url = os.environ.get("OWCS_TEST_DATABASE_URL")
    if not db_url:
        pytest.skip("OWCS_TEST_DATABASE_URL not set")
    from agg_support import build_scratch_db

    conn, raw_conn = build_scratch_db(db_url, os.environ.get("OWCS_TEST_SCHEMA", "owcs_test"))
    yield conn
    conn.close()
    raw_conn.close()
