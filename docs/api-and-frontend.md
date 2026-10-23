# HTTP API and frontend

The answer contract the API returns and the frontend that renders it.

## HTTP API

```bash
pip install -e ".[api]"
python -m owcsmuse serve                      # http://127.0.0.1:8000, /docs for the OpenAPI page
python -m owcsmuse serve --host 0.0.0.0 --port 8080
```

Three endpoints, all read-only, over the same `ask()` pipeline the CLI uses - so
there is one definition of what an answer is, and no SQL is written anywhere in
the web layer.

| endpoint | what it does |
|---|---|
| `POST /ask` | a question in, an answer object out |
| `GET /query/{slug}` | the same question re-run against current data, from a shareable link |
| `GET /suggestions` | example questions built from entities that actually have data |
| `GET /healthz` | liveness plus a database round trip |
| `GET /` | what the service is, and the known limitations by id |

```bash
curl -s localhost:8000/ask -H 'content-type: application/json' \
  -d '{"question": "Sugarfree map record against Zeruhh", "page_size": 5}'
```

```jsonc
{
  "slug": "V5iNpKcbhata",
  "url": "/query/V5iNpKcbhata",
  "status": "ok",                       // ok | clarify | cannot_answer
  "sentence": {
    "text": "sug2rfree is 22-20 in maps against zeruhh across 2024-2026.",
    "spans": [ {"start": 0, "end": 9, "kind": "player", "text": "sug2rfree", "entity_id": "..."} ]
  },
  "aggregate": {
    "description": "player vs player, map grain",
    "columns": [{"key": "map_wins", "label": "Map wins", "type": "integer"}, ...],
    "rows": [ ... ]
  },
  "evidence": {
    "available": true, "grain": "map", "description": "every map behind this record",
    "page": 1, "page_size": 5, "total_rows": 42, "total_pages": 9, "has_more": true,
    "expanded_for": null, "expandable_by": null,
    "columns": [{"key": "played_at", "label": "Date", "type": "date"},
                {"key": "score", "label": "Score", "type": "score", "pair_key": "opponent_score"}, ...],
    "rows": [ {"played_at": "2026-07-04T22:47:50Z", "competition": "S9 NA OWCS Central - Playoffs",
               "team": "SpaceStation Gaming", "opponent": "Team Liquid", "map_name": "Ilios",
               "game_mode": "Control", "score": 2, "opponent_score": 1, "result": "won",
               "eliminations": 20, "deaths": 10, "assists": 2,
               "match_url": "https://www.faceit.com/en/ow2/room/1-1985af81-..."} ]
  },
  "coverage": { ... }, "limitations": [ ... ], "notes": [ ... ],
  "attribution": null,     // {source, license, license_url, pages[]} whenever a Liquipedia value fed the answer
  "entities": { ... }, "query": { ... },   // the structured query it understood
  "code": null, "reason": null,
  "suggestions": [],       // advice, when advice is the answer ("check the spelling")
  "alternatives": [],      // questions that do work, ready to run
  "parser": "rules"
}
```

### Column descriptors

Rows carry raw values, so anything reading them can sort, sum or plot. What each
column *is* comes with it, from `owcsmuse/nlq/columns.py`:

```jsonc
{"key": "played_at", "label": "Date", "type": "date"}
{"key": "score", "label": "Score", "type": "score", "pair_key": "opponent_score"}
{"key": "coverage_pct", "label": "Coverage %", "type": "percent"}
```

`type` is the formatting contract - `date`, `score`, `percent`, `integer`,
`decimal`, `text`, `link`, `flag`, `result`, `list` - and it is decided from the
values as well as the name, so a Postgres `numeric` holding whole numbers is an
`integer` column and a damage total does not render as `9730.00`. Join keys
(`match_id`, `player_id`, `org_key`) stay in the rows and are never described as
columns: a client needs them, a reader does not. A column that is empty at this
grain is left out, which is how a series answer has no "Map #".

A ranked row also carries `entity: {id, type, name, column}`, so expanding it is
mechanical rather than a guess about which column holds the id.

`status` is part of the body, not the HTTP code: a refusal or a clarification is
a real answer with a reason code, so `POST /ask` returns 200 for all three and
reserves 422 for a malformed request and 404 for an unknown slug. A database that
cannot be read is **503 on every endpoint**, `/ask` included - the service is up
and nothing was refused, and a client must be able to say so.

### Evidence rows

Every answer that summarises something carries the rows that produce it, at the
grain the claim was made at: a map record returns each map, a series record
returns each series. They come from the same fact views as the aggregate and
carry the same filters, so they add up to it - `tests/test_api.py` pages through
them and checks exactly that.

- Newest first, `page` / `page_size` (default 25, max 200), with `total_rows`,
  `total_pages` and `has_more` from one query.
- Each row carries the date, competition, both sides, map, mode, score, result,
  the subject's stat line, and `match_url`, the FACEIT room it came from.
- A series row carries `map_stats_recorded`, so a `result_only` series is
  visibly a series with no maps rather than a gap.
- A ranking is a claim about many rows, so one page of evidence can only be
  about one of them: `expanded_for` says which (the top row by default),
  `expandable_by` names the field to pass back, and `evidence_for` asks for
  another. A map or mode breakdown expands the same way.
- When a map record is empty **because the maps were never recorded**, the
  evidence is the series themselves - the proof that the pairing happened and
  the stats did not.

### Answer sentences

One deterministic sentence per intent, built from a template and the rows that
came back (`owcsmuse/nlq/sentence.py`). No model writes it: every number is read
out of a returned row, so the same question on the same data always produces the
same words, and a template that lacks a value it needs degrades to a shorter
sentence instead of inventing one. `tests/test_sentence.py` asserts that every
digit group in a sentence appears in the row behind it.

Entity mentions carry character offsets and the entity id they resolved to, so a
client can link a name without re-parsing the text.

### Choosing between candidates

An ambiguous name returns `status: "clarify"` with the candidates, and **each
candidate carries a `question` that resolves to exactly that entity**:

```jsonc
{"entity_type": "org",  "entity_id": "team-peps", "current_name": "Team Peps",
 "matches": 55, "seasons": [2024, 2025, 2026],
 "first_at": "2024-03-08T...", "last_at": "2026-05-27T...",
 "question": "org:team-peps record"}
```

The question is the original one with the ambiguous name replaced by the entity's
id, so the season, map or opponent in it survives. A client must never build this
itself by substituting a name - substituting a name is exactly what fails when
two entities share one. The parser accepts `player:`, `team:` and `org:` prefixed
ids anywhere a name can appear, and a bare FACEIT GUID as well.

`seasons`, `first_at` and `last_at` are what tell two same-named entities apart:
"Team Falcons, 4 matches, season 2024" against "Team Falcons, no matches".

### Refusals that go somewhere

`suggestions` is advice and stays advice where advice is the answer ("check the
spelling"). `alternatives` are runnable questions, built from what the service
already knows: the entities it resolved, and which seasons actually carry the
stat.

```
Team Falcons and Crazy Raccoons met, but none of those series has map stats on FACEIT
  try: Team Falcons series record against Crazy Raccoons     <- series grain counts them
  try: Team Falcons record
  try: Crazy Raccoons record

'Final Blows' is not recorded for the 2024 season (seasons with it: 2025, 2026)
  try: who had the most final blows in 2026

KOREA is a results-only region: no source records player stats there, so there is no player leaderboard to give
  try: who had the most eliminations                       <- the same question where stats exist
```

The question that just failed is never offered back.

### Shareable links

A slug is a digest of the normalized question, so the same ask always produces
the same link and "who had the most eliminations in 2024" and
"WHO had the most  eliminations in 2024" share one. `saved_queries` stores the
question, never the answer: a link re-runs against current data, which is the
point of sharing it.

`GET /query/{slug}` compares the parse saved with the link against today's and
returns the verdict, so no client diffs two objects to find out:

```jsonc
"shared": {"times_asked": 3, "parsed_when_saved": { ... },
           "parse_changed": true, "parse_change": ["intent: head_to_head -> versus"]}
```

### Query log

Every `POST /ask` and every shared-link re-run writes one `query_log` row: the
question, its status (`ok`, `clarify`, `refusal`, or `error` for an exception),
the reason code, the parse, the resolved entities, the aggregate row count and
the pipeline latency. Nothing about the asker is stored: no IP, user agent,
session or cookie. A question is text someone typed, and it stays only text.

Logging never costs the asker their answer. An answer's row is written in a
background task after the response has gone out, and `querylog.record` swallows
any failure into a `query_log_not_written` warning. An exception's row is
written before the error response, except when the connection itself broke:
the database is then down, and a fresh connect would only delay the 503. A
request rejected by validation (an empty question, or one over 500 characters)
never reaches the pipeline and is not logged.

```bash
python -m owcsmuse queries                    # everything logged
python -m owcsmuse queries --since 7d         # the last week
python -m owcsmuse queries --source ask       # only POST /ask, not shared-link re-runs
python -m owcsmuse queries --from-saved       # saved_queries re-asked through today's parser
python -m owcsmuse queries --json
```

The report shows failures by reason code (most asked first), questions that
parsed to nothing, questions that found no rows, the most asked questions
overall and the most asked that failed. It also shows clusters of failing
phrasings. A cluster is questions that failed the same way and share a shape
once names, seasons and entity ids are taken out (`<player> series record
against <opponent> in <season>`), so twenty variants of one bug read as one
line. The grouping is greedy word overlap: it is a reading aid, and the
examples under each cluster show what it joined.

`--from-saved` covers the time before the log existed. `saved_queries` never
recorded outcomes, so it asks every saved question again, read-only. The result
is what the question gets *today*, not what its asker saw then.

**Size and retention.** Measured on 3,190 rows built from real questions, a row
costs 493 bytes with its indexes, so about **0.5 MB per thousand questions**.
The first month of the beta was 582 asks, about 0.3 MB. Supabase's free tier
allows 500 MB and the database held 304 MB on 2026-10-17, so the log could take
some 400,000 questions before it mattered. No retention job runs. When the
table passes 25 MB (about 50,000 questions), keep failures longer than
successes, because failures are what the log is for:

```sql
DELETE FROM query_log WHERE status = 'ok' AND asked_at < now() - interval '90 days';
DELETE FROM query_log WHERE asked_at < now() - interval '365 days';
```

### Suggestions

Built from the warehouse, not hardcoded: the stat keys, teams and players in
`/suggestions` are the ones with the most data, so a suggested question never
teaches a new visitor that the tool returns nothing. A test asks the first few
and asserts none of them comes back empty.

## Frontend

```bash
python -m owcsmuse serve                      # the API, on :8000
cd web && npm install && npm run dev          # the app, on :5173, proxying to it
npm test                                      # component tests, no server needed
npm run build                                 # static files in web/dist
```

Vite + React, plain CSS, no UI framework and no router: two routes (`/` and
`/q/<slug>`) are thirty lines of `history.pushState` in `src/router.js`, which is
less code than configuring a router would be. `OWCS_API_URL` moves the dev proxy;
`VITE_API_BASE` points a build at a deployed service. The static host must rewrite
unknown paths to `index.html`, or a shared `/q/<slug>` link 404s before the app
loads; `web/vercel.json` does that on Vercel.

The landing page is a question box and three or four examples taken live from
`/suggestions`, so every example has data behind it. Everything else is the
result view:

- **The sentence**, large, at the top. Entity names are links, and they are found
  by the API's character offsets - the text is sliced at `start`/`end` and never
  searched for a name. A nickname that is also an ordinary word, or a name that
  appears twice as two different entities, stays right.
- **Coverage, notes and limitations** sit between the sentence and the table. A
  leaderboard that covers 2025 and 2026 but not 2024 says so above the numbers,
  not in a tooltip or a footer.
- **The evidence table**, rendering the columns the API described - label and
  type - so a map-grain answer shows maps and a series-grain answer shows series
  with no client-side knowledge of either. The client holds no label table and no
  key-name formatter; it formats by `type`, which is why a new column renders
  correctly the day the warehouse grows one.
- **Paging** follows `page` / `total_pages` / `has_more`, newest first.
- **Ranked answers** expand one row at a time: the expanded row is marked in the
  ranking, the evidence header names it, and any other row can be expanded
  through `evidence_for`.
- Below 720px the same table markup becomes cards, using the column label each
  cell already carries. No second component, no horizontal scrolling on a phone.

### The states that are not answers

Built first, because they are common:

- **clarify** renders the candidates as options with what separates them - kind,
  matches in scope, the seasons they were active, and the id when two of them
  share a name. Picking one sends the `question` the service shipped with that
  candidate, verbatim; the client constructs nothing.
- **cannot_answer** shows the reason plainly, the API's advice, and the API's
  `alternatives` - questions that do work - falling back to live suggestions only
  when the service has nothing specific to offer.
- **cannot_answer with evidence** is the informative refusal: a map record that
  is empty because FACEIT never recorded the maps still renders the series behind
  it, flagged as having no map stats.
- **Service failures** are kept apart from refusals: 503 says the service is
  unavailable, a failed `fetch` says it could not be reached, 404 on a shared
  link says the link has nothing behind it. None of them look like a question
  that was understood and declined.

`web/tests/` covers all of the above with payloads captured from the running
service (`tests/fixtures.js`), so the tests exercise what the API actually
sends. `npm test` runs them against a mocked `fetch`; nothing contacts a server.
