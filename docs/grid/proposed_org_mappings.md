# Proposed team-to-org mappings

**Proposals only. Nothing here is applied, loaded or used by any puzzle.** Muse's rule is that a person reviews
every team-to-org mapping, and this document exists for that review. Written 2026-11-17 on `grid/categories`
from read-only queries.

## Why this matters to Grid

49 FACEIT team ids with series in scope are not mapped to an organisation: 49 of the 118 team identities Muse
holds. Grid's rules for them:

- An unmapped team **cannot be a "Played for" clue**. `OrgClue` refuses a `team:<id>` key.
- "Played for 3+ orgs" is **not in the puzzle pool**: it has 15 answers, and 283 players would return "can't verify",
  almost all because of a stint on an unmapped team.
- Twisted Minds, Toronto Defiant, ENCE and M80 are among the best-known teams in the data and are all unmapped.

## What was and was not used as evidence

Used: the names FACEIT recorded on the id (`team_names`), the dates and regions of its series, whether another
identity carries the same name, existing reviewed windows on the id (`team_orgs`), and the Liquipedia team page
named on its linked series (`liquipedia_matches.team*_page`).

**Not used: roster overlap.** A roster that moved is not the organisation moving, and one organisation fields
different rosters (`docs/identity.md`). Not used either: continuity of the FACEIT id. An id follows a roster and
can be reused by unrelated teams, so "one id" is not "one organisation". The confidence below is confidence that
*the name on this id, over these dates, is one organisation by that name*. It says nothing about ownership.

| Confidence | Rule | Count |
|---|---|---|
| High | one FACEIT name throughout, one home region, a Liquipedia page on its series, 10+ series, no other window on the id, no other identity with that name | 10 |
| Medium | as High but under 10 series; or the id carried more than one name; or the id has a reviewed window for another org in another era | 33 |
| Low | another identity shares the name; or series in both NA and EMEA; or no Liquipedia page | 6 |

## How to apply one, if you agree

Not by copying the JSON below into the file. Use Muse's own command, which validates the id and records the
decision, then load and refresh:

```bash
python -m owcsmuse orgs decide <team_id> --org <org-id> --org-name "Name" --note "..."     # add --to <date> for a bounded era
python -m owcsmuse orgs load
python -m owcsmuse refresh && python -m owcsmuse check
```

Then regenerate Grid's puzzles for unpublished dates. A mapping changes `org_key` for every series of that id,
so it changes Muse's own answers too (a team record that was `team:<id>` becomes the org's).

## The ones that matter most for Grid

Ordered by how many players have maps for the team: these are the "Played for" clues a mapping would unlock.

| Team | FACEIT team id | Series | Dates | Regions | Players with maps | Liquipedia | Confidence |
|---|---|---|---|---|---|---|---|
| Twisted Minds | `2b9f2e7a-f91a-4597-b2fa-d413eaed605e` | 116 | 2024-03-08 to 2026-11-01 | emea, international | 15 | [Twisted Minds](https://liquipedia.net/overwatch/Twisted_Minds) | **High** |
| Shikigami | `ec69a520-047f-4754-b36e-b0c95e2066ff` | 23 | 2024-03-08 to 2025-02-23 | na | 12 | [Shikigami](https://liquipedia.net/overwatch/Shikigami) | **High** |
| Citrus Nation | `35fd77ed-a916-4f76-aafd-af3d57ad84cb` | 21 | 2024-03-08 to 2024-10-10 | na | 10 | [Citrus Nation](https://liquipedia.net/overwatch/Citrus_Nation) | **High** |
| M80 | `3aca5abd-ee5d-4542-92e9-392b6f5d0dbc` | 22 | 2024-03-08 to 2024-07-26 | international, na | 9 | [M80](https://liquipedia.net/overwatch/M80) | **High** |
| The Ultimates | `3eaeefbc-6abf-4d54-aeb2-2790e3e21752` | 22 | 2025-01-31 to 2025-06-28 | emea | 9 | [The Ultimates](https://liquipedia.net/overwatch/The_Ultimates) | **High** |
| AWW YEAH | `90b2fd83-bb47-4286-8f62-a16eb6ce650b` | 14 | 2024-03-08 to 2024-08-29 | emea | 9 | [AWW YEAH](https://liquipedia.net/overwatch/AWW_YEAH) | **High** |
| Timeless | `c5116cb3-1e5d-457f-9c4a-52a5dd75ab6e` | 30 | 2024-03-08 to 2025-03-08 | na | 9 | [Timeless](https://liquipedia.net/overwatch/Timeless) | **Medium** |
| Daybreak | `cce69e3f-b11e-4635-8370-8ddd371f690a` | 5 | 2024-03-08 to 2024-04-14 | na | 9 | [Daybreak (team)](https://liquipedia.net/overwatch/Daybreak_(team)) | **Medium** |
| Ex Oblivione | `bb5dd404-213c-430f-8d12-8687fc3ff747` | 17 | 2024-03-08 to 2024-10-06 | emea | 8 | [Ex Oblivione](https://liquipedia.net/overwatch/Ex_Oblivione) | **Medium** |
| PxG PiP | `f4401a61-5010-484b-8429-ad09e524b097` | 13 | 2024-03-08 to 2024-04-29 | na | 8 | [Pirates in Pyjamas](https://liquipedia.net/overwatch/Pirates_in_Pyjamas) | **Medium** |
| TML Nightmare | `dc443c37-abc3-4e69-9e4c-56f966f64d8b` | 2 | 2024-04-12 to 2024-04-20 | na | 8 | [Nightmare Rotation](https://liquipedia.net/overwatch/Nightmare_Rotation) | **Medium** |
| Luminosity | `d4ec89d7-7d41-4c0e-9834-fbf87a199347` | 13 | 2024-03-08 to 2024-04-29 | na | 7 | [Luminosity Gaming](https://liquipedia.net/overwatch/Luminosity_Gaming) | **High** |
| Avidity | `2b7f8ef6-bb71-4d2f-a66c-5d2a571138ae` | 12 | 2024-08-16 to 2025-03-02 | na | 7 | [Avidity](https://liquipedia.net/overwatch/Avidity) | **Medium** |
| UNC inc | `0464a373-df2f-4d23-93f5-80cbaa07802f` | 3 | 2024-04-12 to 2024-04-21 | na | 7 | [UNC INC](https://liquipedia.net/overwatch/UNC_INC) | **Medium** |

### Twisted Minds (`2b9f2e7a`): High

- **Why this confidence:** one name throughout, one region, a Liquipedia page, 10+ series, no other window on the id.
- **FACEIT names on the id:** Twisted Minds (2024-03-08 to 2026-10-24).
- **Series:** 116, 2024-03-08 to 2026-11-01. Seasons 2024, 2025, 2026. Regions: emea, international.
- **Stages played:** Esports World Cup 2024, 2024 Dreamhack Dallas, 2024 EMEA Stage 1, 2024 EMEA Stage 2, 2024 EMEA Stage 3, 2024 EMEA Stage 4, 2024 World Finals, 2025 EMEA Stage 1, and 9 more.
- **Liquipedia:** https://liquipedia.net/overwatch/Twisted_Minds
- **Grid effect:** 15 players would become "Played for Twisted Minds" answers.

```json
{
  "2b9f2e7a-f91a-4597-b2fa-d413eaed605e": {
    "org_id": "twisted-minds",
    "org_name": "Twisted Minds",
    "team_name": "Twisted Minds",
    "note": "PROPOSED by the Grid categories audit (2026-11-17), not reviewed. One name throughout, one region, a liquipedia page, 10+ series, no other window on the id.",
    "evidence": [
      "FACEIT names on this id: Twisted Minds",
      "116 series in scope, 2024-03-08..2026-11-01; seasons 2024, 2025, 2026; regions emea, international",
      "Liquipedia team page on its series: https://liquipedia.net/overwatch/Twisted_Minds",
      "roster overlap was not used: it is not evidence of org identity"
    ]
  }
}
```

### Shikigami (`ec69a520`): High

- **Why this confidence:** one name throughout, one region, a Liquipedia page, 10+ series, no other window on the id.
- **FACEIT names on the id:** Shikigami (2024-03-08 to 2025-02-23).
- **Series:** 23, 2024-03-08 to 2025-02-23. Seasons 2024, 2025. Regions: na.
- **Stages played:** 2024 NA Stage 1, 2024 NA Stage 2, 2024 NA Stage 3, 2024 NA Stage 4, 2025 NA Stage 1.
- **Liquipedia:** https://liquipedia.net/overwatch/Shikigami
- **Grid effect:** 12 players would become "Played for Shikigami" answers.

```json
{
  "ec69a520-047f-4754-b36e-b0c95e2066ff": {
    "org_id": "shikigami",
    "org_name": "Shikigami",
    "team_name": "Shikigami",
    "note": "PROPOSED by the Grid categories audit (2026-11-17), not reviewed. One name throughout, one region, a liquipedia page, 10+ series, no other window on the id.",
    "evidence": [
      "FACEIT names on this id: Shikigami",
      "23 series in scope, 2024-03-08..2025-02-23; seasons 2024, 2025; regions na",
      "Liquipedia team page on its series: https://liquipedia.net/overwatch/Shikigami",
      "roster overlap was not used: it is not evidence of org identity"
    ]
  }
}
```

### Citrus Nation (`35fd77ed`): High

- **Why this confidence:** one name throughout, one region, a Liquipedia page, 10+ series, no other window on the id.
- **FACEIT names on the id:** Citrus Nation (2024-03-08 to 2024-04-29).
- **Series:** 21, 2024-03-08 to 2024-10-10. Seasons 2024. Regions: na.
- **Stages played:** 2024 NA Stage 1, 2024 NA Stage 2, 2024 NA Stage 3, 2024 NA Stage 4.
- **Liquipedia:** https://liquipedia.net/overwatch/Citrus_Nation
- **Grid effect:** 10 players would become "Played for Citrus Nation" answers.

```json
{
  "35fd77ed-a916-4f76-aafd-af3d57ad84cb": {
    "org_id": "citrus-nation",
    "org_name": "Citrus Nation",
    "team_name": "Citrus Nation",
    "note": "PROPOSED by the Grid categories audit (2026-11-17), not reviewed. One name throughout, one region, a liquipedia page, 10+ series, no other window on the id.",
    "evidence": [
      "FACEIT names on this id: Citrus Nation",
      "21 series in scope, 2024-03-08..2024-10-10; seasons 2024; regions na",
      "Liquipedia team page on its series: https://liquipedia.net/overwatch/Citrus_Nation",
      "roster overlap was not used: it is not evidence of org identity"
    ]
  }
}
```

### M80 (`3aca5abd`): High

- **Why this confidence:** one name throughout, one region, a Liquipedia page, 10+ series, no other window on the id.
- **FACEIT names on the id:** M80 (2024-03-08 to 2024-06-02).
- **Series:** 22, 2024-03-08 to 2024-07-26. Seasons 2024. Regions: international, na.
- **Stages played:** Esports World Cup 2024, 2024 Dreamhack Dallas, 2024 NA Stage 1, 2024 NA Stage 2.
- **Liquipedia:** https://liquipedia.net/overwatch/M80
- **Grid effect:** 9 players would become "Played for M80" answers.

```json
{
  "3aca5abd-ee5d-4542-92e9-392b6f5d0dbc": {
    "org_id": "m80",
    "org_name": "M80",
    "team_name": "M80",
    "note": "PROPOSED by the Grid categories audit (2026-11-17), not reviewed. One name throughout, one region, a liquipedia page, 10+ series, no other window on the id.",
    "evidence": [
      "FACEIT names on this id: M80",
      "22 series in scope, 2024-03-08..2024-07-26; seasons 2024; regions international, na",
      "Liquipedia team page on its series: https://liquipedia.net/overwatch/M80",
      "roster overlap was not used: it is not evidence of org identity"
    ]
  }
}
```

### The Ultimates (`3eaeefbc`): High

- **Why this confidence:** one name throughout, one region, a Liquipedia page, 10+ series, no other window on the id.
- **FACEIT names on the id:** The Ultimates (2025-01-31 to 2025-06-28).
- **Series:** 22, 2025-01-31 to 2025-06-28. Seasons 2025. Regions: emea.
- **Stages played:** 2025 EMEA Stage 1, 2025 EMEA Stage 2.
- **Liquipedia:** https://liquipedia.net/overwatch/The_Ultimates
- **Grid effect:** 9 players would become "Played for The Ultimates" answers.

```json
{
  "3eaeefbc-6abf-4d54-aeb2-2790e3e21752": {
    "org_id": "the-ultimates",
    "org_name": "The Ultimates",
    "team_name": "The Ultimates",
    "note": "PROPOSED by the Grid categories audit (2026-11-17), not reviewed. One name throughout, one region, a liquipedia page, 10+ series, no other window on the id.",
    "evidence": [
      "FACEIT names on this id: The Ultimates",
      "22 series in scope, 2025-01-31..2025-06-28; seasons 2025; regions emea",
      "Liquipedia team page on its series: https://liquipedia.net/overwatch/The_Ultimates",
      "roster overlap was not used: it is not evidence of org identity"
    ]
  }
}
```

### AWW YEAH (`90b2fd83`): High

- **Why this confidence:** one name throughout, one region, a Liquipedia page, 10+ series, no other window on the id.
- **FACEIT names on the id:** AWW YEAH (2024-03-08 to 2024-04-29).
- **Series:** 14, 2024-03-08 to 2024-08-29. Seasons 2024. Regions: emea.
- **Stages played:** 2024 EMEA Stage 1, 2024 EMEA Stage 2, 2024 EMEA Stage 3.
- **Liquipedia:** https://liquipedia.net/overwatch/AWW_YEAH
- **Grid effect:** 9 players would become "Played for AWW YEAH" answers.

```json
{
  "90b2fd83-bb47-4286-8f62-a16eb6ce650b": {
    "org_id": "aww-yeah",
    "org_name": "AWW YEAH",
    "team_name": "AWW YEAH",
    "note": "PROPOSED by the Grid categories audit (2026-11-17), not reviewed. One name throughout, one region, a liquipedia page, 10+ series, no other window on the id.",
    "evidence": [
      "FACEIT names on this id: AWW YEAH",
      "14 series in scope, 2024-03-08..2024-08-29; seasons 2024; regions emea",
      "Liquipedia team page on its series: https://liquipedia.net/overwatch/AWW_YEAH",
      "roster overlap was not used: it is not evidence of org identity"
    ]
  }
}
```

### Timeless (`c5116cb3`): Medium

- **Why this confidence:** the id also belongs to a reviewed org in another era; this is the era outside that window.
- **FACEIT names on the id:** Timeless (2024-03-08 to 2025-03-08); NTMR (2025-05-10 to 2025-10-19).
- **Series:** 30, 2024-03-08 to 2025-03-08. Seasons 2024, 2025. Regions: na.
- **Stages played:** 2024 NA Stage 1, 2024 NA Stage 2, 2024 NA Stage 3, 2025 NA Stage 1.
- **Liquipedia:** https://liquipedia.net/overwatch/Timeless
- **Existing reviewed windows on this id:** `ntmr` from 2025-05-10 to infinity. The proposal covers only the era outside them.
- **Grid effect:** 9 players would become "Played for Timeless" answers.

```json
{
  "c5116cb3-1e5d-457f-9c4a-52a5dd75ab6e": {
    "org_id": "timeless",
    "org_name": "Timeless",
    "team_name": "NTMR",
    "note": "PROPOSED by the Grid categories audit (2026-11-17), not reviewed. The id also belongs to a reviewed org in another era; this is the era outside that window.",
    "evidence": [
      "FACEIT names on this id: Timeless, NTMR",
      "30 series in scope, 2024-03-08..2025-03-08; seasons 2024, 2025; regions na",
      "Liquipedia team page on its series: https://liquipedia.net/overwatch/Timeless",
      "roster overlap was not used: it is not evidence of org identity",
      "existing reviewed window on this id: ntmr from 2025-05-10"
    ],
    "valid_to": "2025-05-10T00:00:00+00:00"
  }
}
```

### Daybreak (`cce69e3f`): Medium

- **Why this confidence:** one name and a Liquipedia page, but under 10 series.
- **FACEIT names on the id:** Daybreak (2024-03-08 to 2024-04-14).
- **Series:** 5, 2024-03-08 to 2024-04-14. Seasons 2024. Regions: na.
- **Stages played:** 2024 NA Stage 1, 2024 NA Stage 2.
- **Liquipedia:** https://liquipedia.net/overwatch/Daybreak_(team)
- **Grid effect:** 9 players would become "Played for Daybreak" answers.

```json
{
  "cce69e3f-b11e-4635-8370-8ddd371f690a": {
    "org_id": "daybreak",
    "org_name": "Daybreak",
    "team_name": "Daybreak",
    "note": "PROPOSED by the Grid categories audit (2026-11-17), not reviewed. One name and a liquipedia page, but under 10 series.",
    "evidence": [
      "FACEIT names on this id: Daybreak",
      "5 series in scope, 2024-03-08..2024-04-14; seasons 2024; regions na",
      "Liquipedia team page on its series: https://liquipedia.net/overwatch/Daybreak_(team)",
      "roster overlap was not used: it is not evidence of org identity"
    ]
  }
}
```

### Ex Oblivione (`bb5dd404`): Medium

- **Why this confidence:** the id also belongs to a reviewed org in another era; this is the era outside that window.
- **FACEIT names on the id:** Ex Oblivione (2024-03-08 to 2024-04-20); Virtuspro (2025-01-31 to 2025-10-19).
- **Series:** 17, 2024-03-08 to 2024-10-06. Seasons 2024. Regions: emea.
- **Stages played:** 2024 EMEA Stage 1, 2024 EMEA Stage 2, 2024 EMEA Stage 3, 2024 EMEA Stage 4.
- **Liquipedia:** https://liquipedia.net/overwatch/Ex_Oblivione
- **Existing reviewed windows on this id:** `virtus-pro` from 2025-01-31 to infinity. The proposal covers only the era outside them.
- **Grid effect:** 8 players would become "Played for Ex Oblivione" answers.

```json
{
  "bb5dd404-213c-430f-8d12-8687fc3ff747": {
    "org_id": "ex-oblivione",
    "org_name": "Ex Oblivione",
    "team_name": "Virtuspro",
    "note": "PROPOSED by the Grid categories audit (2026-11-17), not reviewed. The id also belongs to a reviewed org in another era; this is the era outside that window.",
    "evidence": [
      "FACEIT names on this id: Ex Oblivione, Virtuspro",
      "17 series in scope, 2024-03-08..2024-10-06; seasons 2024; regions emea",
      "Liquipedia team page on its series: https://liquipedia.net/overwatch/Ex_Oblivione",
      "roster overlap was not used: it is not evidence of org identity",
      "existing reviewed window on this id: virtus-pro from 2025-01-31"
    ],
    "valid_to": "2025-01-31T00:00:00+00:00"
  }
}
```

### PxG PiP (`f4401a61`): Medium

- **Why this confidence:** the id carried more than one name.
- **FACEIT names on the id:** PIP (2024-03-08 to 2024-04-12); PxG PiP (2024-04-14 to 2024-04-29).
- **Series:** 13, 2024-03-08 to 2024-04-29. Seasons 2024. Regions: na.
- **Stages played:** 2024 NA Stage 1, 2024 NA Stage 2.
- **Liquipedia:** https://liquipedia.net/overwatch/Pirates_in_Pyjamas
- **Grid effect:** 8 players would become "Played for PxG PiP" answers.

```json
{
  "f4401a61-5010-484b-8429-ad09e524b097": {
    "org_id": "pxg-pip",
    "org_name": "PxG PiP",
    "team_name": "PxG PiP",
    "note": "PROPOSED by the Grid categories audit (2026-11-17), not reviewed. The id carried more than one name.",
    "evidence": [
      "FACEIT names on this id: PIP, PxG PiP",
      "13 series in scope, 2024-03-08..2024-04-29; seasons 2024; regions na",
      "Liquipedia team page on its series: https://liquipedia.net/overwatch/Pirates_in_Pyjamas",
      "roster overlap was not used: it is not evidence of org identity"
    ]
  }
}
```

### TML Nightmare (`dc443c37`): Medium

- **Why this confidence:** one name and a Liquipedia page, but under 10 series.
- **FACEIT names on the id:** TML Nightmare (2024-04-12 to 2024-04-20).
- **Series:** 2, 2024-04-12 to 2024-04-20. Seasons 2024. Regions: na.
- **Stages played:** 2024 NA Stage 2.
- **Liquipedia:** https://liquipedia.net/overwatch/Nightmare_Rotation
- **Grid effect:** 8 players would become "Played for TML Nightmare" answers.

```json
{
  "dc443c37-abc3-4e69-9e4c-56f966f64d8b": {
    "org_id": "tml-nightmare",
    "org_name": "TML Nightmare",
    "team_name": "TML Nightmare",
    "note": "PROPOSED by the Grid categories audit (2026-11-17), not reviewed. One name and a liquipedia page, but under 10 series.",
    "evidence": [
      "FACEIT names on this id: TML Nightmare",
      "2 series in scope, 2024-04-12..2024-04-20; seasons 2024; regions na",
      "Liquipedia team page on its series: https://liquipedia.net/overwatch/Nightmare_Rotation",
      "roster overlap was not used: it is not evidence of org identity"
    ]
  }
}
```

### Luminosity (`d4ec89d7`): High

- **Why this confidence:** one name throughout, one region, a Liquipedia page, 10+ series, no other window on the id.
- **FACEIT names on the id:** Luminosity (2024-03-08 to 2024-04-29).
- **Series:** 13, 2024-03-08 to 2024-04-29. Seasons 2024. Regions: na.
- **Stages played:** 2024 NA Stage 1, 2024 NA Stage 2.
- **Liquipedia:** https://liquipedia.net/overwatch/Luminosity_Gaming
- **Grid effect:** 7 players would become "Played for Luminosity" answers.

```json
{
  "d4ec89d7-7d41-4c0e-9834-fbf87a199347": {
    "org_id": "luminosity",
    "org_name": "Luminosity",
    "team_name": "Luminosity",
    "note": "PROPOSED by the Grid categories audit (2026-11-17), not reviewed. One name throughout, one region, a liquipedia page, 10+ series, no other window on the id.",
    "evidence": [
      "FACEIT names on this id: Luminosity",
      "13 series in scope, 2024-03-08..2024-04-29; seasons 2024; regions na",
      "Liquipedia team page on its series: https://liquipedia.net/overwatch/Luminosity_Gaming",
      "roster overlap was not used: it is not evidence of org identity"
    ]
  }
}
```

### Avidity (`2b7f8ef6`): Medium

- **Why this confidence:** the id also belongs to a reviewed org in another era; this is the era outside that window.
- **FACEIT names on the id:** Avidity (2025-02-01 to 2025-03-02); Extinction (2025-05-11 to 2025-10-12).
- **Series:** 12, 2024-08-16 to 2025-03-02. Seasons 2024, 2025. Regions: na.
- **Stages played:** 2024 NA Stage 3, 2025 NA Stage 1.
- **Liquipedia:** https://liquipedia.net/overwatch/Avidity
- **Existing reviewed windows on this id:** `extinction` from 2025-05-11 to infinity. The proposal covers only the era outside them.
- **Grid effect:** 7 players would become "Played for Avidity" answers.

```json
{
  "2b7f8ef6-bb71-4d2f-a66c-5d2a571138ae": {
    "org_id": "avidity",
    "org_name": "Avidity",
    "team_name": "Extinction",
    "note": "PROPOSED by the Grid categories audit (2026-11-17), not reviewed. The id also belongs to a reviewed org in another era; this is the era outside that window.",
    "evidence": [
      "FACEIT names on this id: Avidity, Extinction",
      "12 series in scope, 2024-08-16..2025-03-02; seasons 2024, 2025; regions na",
      "Liquipedia team page on its series: https://liquipedia.net/overwatch/Avidity",
      "roster overlap was not used: it is not evidence of org identity",
      "existing reviewed window on this id: extinction from 2025-05-11"
    ],
    "valid_to": "2025-05-11T00:00:00+00:00"
  }
}
```

### UNC inc (`0464a373`): Medium

- **Why this confidence:** the id also belongs to a reviewed org in another era; this is the era outside that window.
- **FACEIT names on the id:** UNC inc (2024-04-12 to 2024-04-21); Rad (2025-02-01 to 2025-05-10); Sakura (2025-05-17 to 2025-09-21); Sakura Esports (2025-09-27 to 2025-10-25); LuneX (2026-03-21 to 2026-07-04); KAFE (2026-10-11 to 2026-10-24).
- **Series:** 3, 2024-04-12 to 2024-04-21. Seasons 2024. Regions: na.
- **Stages played:** 2024 NA Stage 2.
- **Liquipedia:** https://liquipedia.net/overwatch/UNC_INC
- **Existing reviewed windows on this id:** `rad` from 2025-02-01 to 2025-05-01; `sakura` from 2025-05-01 to 2026-03-21; `lunex` from 2026-03-21 to 2026-10-09; `kafe` from 2026-10-09 to 2026-11-03. The proposal covers only the era outside them.
- **Grid effect:** 7 players would become "Played for UNC inc" answers.

```json
{
  "0464a373-df2f-4d23-93f5-80cbaa07802f": {
    "org_id": "unc-inc",
    "org_name": "UNC inc",
    "team_name": "KAFE",
    "note": "PROPOSED by the Grid categories audit (2026-11-17), not reviewed. The id also belongs to a reviewed org in another era; this is the era outside that window.",
    "evidence": [
      "FACEIT names on this id: UNC inc, Rad, Sakura, Sakura Esports, LuneX, KAFE",
      "3 series in scope, 2024-04-12..2024-04-21; seasons 2024; regions na",
      "Liquipedia team page on its series: https://liquipedia.net/overwatch/UNC_INC",
      "roster overlap was not used: it is not evidence of org identity",
      "existing reviewed window on this id: rad from 2025-02-01 to 2025-05-01",
      "existing reviewed window on this id: sakura from 2025-05-01 to 2026-03-21",
      "existing reviewed window on this id: lunex from 2026-03-21 to 2026-10-09",
      "existing reviewed window on this id: kafe from 2026-10-09 to 2026-11-03"
    ],
    "valid_to": "2025-02-01T00:00:00+00:00"
  }
}
```

## Notes on specific ids

- **Twisted Minds (`2b9f2e7a`)**: one name on one id from 2024-03-08 to 2026-11-01, EMEA plus international events, the
  most series of any identity (116). The cleanest proposal here. Muse already holds a reviewed *alias* `TM` to this
  team id, which shows it has been looked at as a team, not that it was mapped.
- **ENCE (`62f7752b`)**: the id's first name was `BuboSprayCheck`. `docs/identity.md` records the owner's reading of
  that as a registration placeholder replaced inside the stage (BuboSprayCheck to ENCE). Medium only because the
  rule here does not read that decision; with it, this is as clean as Twisted Minds.
- **Toronto Defiant (`8f632648`)**: 2024 only. `docs/liquipedia.md` records that Toronto Ultra at EWC 2024 is
  Toronto Defiant (owner, 2026-10-09). An org would let that decision name an org, not a bare id.
- **Timeless (`c5116cb3`) and Ex Oblivione (`bb5dd404`)**: each id later belongs to a reviewed org (NTMR from
  2025-05-10; Virtus pro from 2025-01-31). The proposals are bounded with `valid_to` at those dates, in Muse's
  existing window format. The owner already decided these eras are *not* NTMR or Virtus pro; mapping them to an org
  of their own only gives that earlier team a stable id.
- **Geekay Esports (`590b7d3b`, NA 2025; `46f8e560`, EMEA 2026)**: Low. Two unrelated teams share the name, an
  earlier merge of them was reversed, and Muse aliases them as `GK NA` and `GK EMEA`. If mapped, they need two org
  ids. Do not accept the generated `org_id` for either as it stands: both proposals below would collide.
- **Sakura (`b6e7f5e3`, EMEA 2025)**: Low. A reviewed org `sakura` (NA) already exists on a different id.
- **0464a373 and d20d1868** (the recycled ids): every era with series is already mapped or decided. Their bare-id
  eras appear below only for the series outside every window.

## Every unmapped FACEIT team id with series

| Team | Team id | Series | First | Last | Regions | Names on the id | Players with maps | Confidence |
|---|---|---|---|---|---|---|---|---|
| Twisted Minds | `2b9f2e7a` | 116 | 2024-03-08 | 2026-11-01 | emea, international | Twisted Minds | 15 | High |
| Shikigami | `ec69a520` | 23 | 2024-03-08 | 2025-02-23 | na | Shikigami | 12 | High |
| Citrus Nation | `35fd77ed` | 21 | 2024-03-08 | 2024-10-10 | na | Citrus Nation | 10 | High |
| M80 | `3aca5abd` | 22 | 2024-03-08 | 2024-07-26 | international, na | M80 | 9 | High |
| The Ultimates | `3eaeefbc` | 22 | 2025-01-31 | 2025-06-28 | emea | The Ultimates | 9 | High |
| AWW YEAH | `90b2fd83` | 14 | 2024-03-08 | 2024-08-29 | emea | AWW YEAH | 9 | High |
| Luminosity | `d4ec89d7` | 13 | 2024-03-08 | 2024-04-29 | na | Luminosity | 7 | High |
| Toronto Defiant | `8f632648` | 43 | 2024-03-08 | 2024-11-24 | international, na | Toronto Defiant | 6 | High |
| A One Man Army | `6c39d9d5` | 16 | 2024-03-08 | 2024-10-10 | emea | A One Man Army | 6 | High |
| SupershyOW | `98798472` | 12 | 2024-04-12 | 2024-08-29 | emea | SupershyOW | 5 | High |
| Timeless | `c5116cb3` | 30 | 2024-03-08 | 2025-03-08 | na | Timeless, NTMR | 9 | Medium |
| Daybreak | `cce69e3f` | 5 | 2024-03-08 | 2024-04-14 | na | Daybreak | 9 | Medium |
| Ex Oblivione | `bb5dd404` | 17 | 2024-03-08 | 2024-10-06 | emea | Ex Oblivione, Virtuspro | 8 | Medium |
| PxG PiP | `f4401a61` | 13 | 2024-03-08 | 2024-04-29 | na | PIP, PxG PiP | 8 | Medium |
| TML Nightmare | `dc443c37` | 2 | 2024-04-12 | 2024-04-20 | na | TML Nightmare | 8 | Medium |
| Avidity | `2b7f8ef6` | 12 | 2024-08-16 | 2025-03-02 | na | Avidity, Extinction | 7 | Medium |
| UNC inc | `0464a373` | 3 | 2024-04-12 | 2024-04-21 | na | UNC inc, Rad, Sakura, Sakura Esports, LuneX, KAFE | 7 | Medium |
| ENCE | `62f7752b` | 38 | 2024-03-08 | 2024-11-22 | emea, international | BuboSprayCheck, ENCE | 6 | Medium |
| Telacy | `b50813d6` | 9 | 2026-05-25 | 2026-06-28 | emea | Telacy | 6 | Medium |
| Peace and Love | `d8cd2ece` | 7 | 2024-04-12 | 2024-04-29 | emea | Peace and Love | 6 | Medium |
| FMCL | `cefc3f72` | 7 | 2024-04-12 | 2024-04-29 | na | FMCL, NTMR | 6 | Medium |
| Amplify | `c34ba98e` | 7 | 2025-02-01 | 2025-02-22 | na | Amplify | 6 | Medium |
| Metaboiz | `6c2f5887` | 6 | 2024-04-12 | 2024-09-29 | emea | Metaboiz | 6 | Medium |
| LFO | `a24592c1` | 6 | 2024-03-08 | 2024-03-21 | na | LFO | 6 | Medium |
| Deimpero | `c82570d6` | 6 | 2024-04-12 | 2024-04-29 | emea | Deimpero, Frost Tails | 6 | Medium |
| Anyones Legend | `75516399` | 5 | 2026-03-22 | 2026-04-05 | emea | Anyones Legend, 1234 | 6 | Medium |
| EF Flexodiax | `241bb1a3` | 4 | 2024-03-08 | 2024-04-20 | emea | EF Flexodiax | 6 | Medium |
| Celtas | `0dcea68d` | 3 | 2024-03-08 | 2024-03-17 | emea | Celtas | 6 | Medium |
| Dreamland | `d20d1868` | 3 | 2024-03-08 | 2024-03-17 | na | team_chiime, Dreamland, Supernova, Team Z, NTMR | 6 | Medium |
| Bingus | `d2e11bea` | 2 | 2024-03-08 | 2024-03-16 | emea | Bingus | 6 | Medium |
| nah id win | `61a69c78` | 2 | 2024-03-08 | 2024-03-16 | na | nah id win | 6 | Medium |
| Goud Guys ANM | `602d3c11` | 7 | 2025-09-07 | 2025-10-12 | emea | Goud Guys, Goud Guys ANM | 5 | Medium |
| Vice | `3a72be04` | 5 | 2024-04-12 | 2024-08-24 | na | Vice | 5 | Medium |
| ROC ESPORT | `03869857` | 5 | 2024-03-08 | 2024-03-21 | emea | ROC ESPORT, Umbrellaacademy, ROCstars | 5 | Medium |
| Obsidian | `fee18be3` | 3 | 2024-03-08 | 2024-03-17 | na | Obsidian | 5 | Medium |
| nuage | `b696c66d` | 3 | 2024-03-08 | 2024-03-16 | emea | nuage | 5 | Medium |
| LeftRightGnight | `3c56dcad` | 3 | 2024-03-08 | 2024-03-17 | emea | LeftRightGnight | 5 | Medium |
| team_sawhill | `ed04d97f` | 2 | 2024-03-08 | 2024-03-16 | na | team_sawhill | 5 | Medium |
| team_POUNDTOWNBOW | `59999af9` | 2 | 2024-03-08 | 2024-03-10 | na | team_POUNDTOWNBOW | 5 | Medium |
| A-Square Tengu | `ed0289e5` | 2 | 2024-03-08 | 2024-03-10 | emea | A-Square Tengu | 5 | Medium |
| SCHMUNGUS | `865c189c` | 2 | 2024-04-12 | 2024-04-14 | emea | SCHMUNGUS | 5 | Medium |
| Final Gambit | `6ec39b17` | 2 | 2024-03-08 | 2024-03-10 | na | Final Gambit | 5 | Medium |
| Visored | `626ee9e6` | 2 | 2024-04-12 | 2024-04-14 | na | Visored | 5 | Medium |
| Geekay Esports | `46f8e560` | 26 | 2026-03-22 | 2026-10-25 | emea, international | Geekay Esports | 6 | Low |
| Geekay Esports | `590b7d3b` | 28 | 2025-05-11 | 2025-11-28 | international, na | Geekay Esports | 5 | Low |
| Sakura | `b6e7f5e3` | 7 | 2025-01-31 | 2025-02-22 | emea | Sakura | 5 | Low |
| The Kafe | `a35f8d47` | 5 | 2026-06-13 | 2026-06-28 | na | Extinction, The Kafe | 5 | Low |
| Kintsugi | `a791e2fa` | 3 | 2026-05-25 | 2026-05-28 | na | Kintsugi | 5 | Low |
| Star Bits x Hypnos | `444668eb` | 2 | 2026-05-25 | 2026-05-26 | emea | Star Bits x Hypnos | 5 | Low |
